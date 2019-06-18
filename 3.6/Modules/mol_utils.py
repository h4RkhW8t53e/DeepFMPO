from global_parameters import MOL_SPLIT_START, MAX_FREE, MAX_ATOMS, MAX_FRAGMENTS
from rdkit import Chem
import numpy as np
import logging

def drop_salt(s):
    s = s.split(".")
    return [x for _, x in sorted(zip(map(len,s), s), reverse=True)][0]





def okToBreak(bond):
    
    if bond.IsInRing():
        return False
    
    if bond.GetBondType() != Chem.rdchem.BondType.SINGLE:
        return False

    
    begin_atom = bond.GetBeginAtom()
    end_atom = bond.GetEndAtom()
    
    if not(begin_atom.IsInRing() or end_atom.IsInRing()):
        return False
    elif begin_atom.GetAtomicNum() >= MOL_SPLIT_START or \
            end_atom.GetAtomicNum() >= MOL_SPLIT_START:
        return False
    else:
        return True

    


def split_molecule(mol):
    
    split_id = MOL_SPLIT_START
    
    res = []
    to_check = [mol]
    while len(to_check) > 0:
        ms = spf(to_check.pop(), split_id)
        if len(ms) == 1:
            res += ms
        else:
            to_check += ms 
            split_id += 1
    
    return create_chain(res)


def spf(mol, split_id):
    
    bonds = mol.GetBonds()
    for i in range(len(bonds)):
        if okToBreak(bonds[i]):
            mol = Chem.FragmentOnBonds(mol, [i], addDummies=True, dummyLabels=[(0, 0)])
            # Dummy atoms are always added last
            n_at = mol.GetNumAtoms()
            mol.GetAtomWithIdx(n_at-1).SetAtomicNum(split_id)
            mol.GetAtomWithIdx(n_at-2).SetAtomicNum(split_id)
            return Chem.rdmolops.GetMolFrags(mol, asMols=True)
     
    # If the molecule could not been split, return original molecule
    return [mol] 




def create_chain(splits):
    splits_ids = [x for x in [sorted([a.GetAtomicNum() for a in m.GetAtoms()
                          if a.GetAtomicNum() >= MOL_SPLIT_START]) for m in splits]
                  if x]

    splits2 = []

    if not splits_ids:
        return []
    
    mv = max(splits_ids)
    try:
        look_for = [mv if isinstance(mv, np.int64) else mv[0]]
    except:
        logging.exception("no mv: %r", splits_ids)
        raise
    
    join_order = []
    
    mols = []
        
    for i in range(len(splits_ids)):
        l = splits_ids[i]
        if l[0] == look_for[0] and len(l) == 1:
            mols.append(splits[i])
            splits2.append(splits_ids[i])
            try:
                splits_ids[i] = []
            except:
                print(repr(splits_ids[i]))
                raise
    
    splits_ids = np.asarray(splits_ids)
    while len(look_for) > 0:
        sid = look_for.pop()
        join_order.append(sid)
        next_mol = [i for i in range(len(splits_ids))
                      if sid in splits_ids[i]]
        
        if len(next_mol) == 0:
            break
        next_mol = next_mol[0]
        
        for n in splits_ids[next_mol]:
            if n != sid:
                look_for.append(n)
        mols.append(splits[next_mol])
        splits2.append(splits_ids[next_mol])
        splits_ids[next_mol] = []
    
    return [simplify_splits(mols[i], splits2[i], join_order) for i in range(len(mols))]
    

def simplify_splits(mol, splits, join_order):
    
    td = {}
    n = 0
    for i in splits:
        for j in join_order:
            if i == j:
                td[i] = MOL_SPLIT_START + n
                n += 1
    
    for a in mol.GetAtoms():
        k = a.GetAtomicNum()
        if k in td:
            a.SetAtomicNum(td[k])
    
    return mol



def get_join_list(mol):
    
    join = []
    rem = []
    bonds = []
    
    for a in mol.GetAtoms():
        an = a.GetAtomicNum()
        if an >= MOL_SPLIT_START:
            while len(join) <= (an - MOL_SPLIT_START):
                rem.append(None)
                bonds.append(None)
                join.append(None)
                
            b = a.GetBonds()[0]
            ja = b.GetBeginAtom() if b.GetBeginAtom().GetAtomicNum() < MOL_SPLIT_START else \
                 b.GetEndAtom()
            join[an - MOL_SPLIT_START] = ja.GetIdx()
            rem[an - MOL_SPLIT_START] = a.GetIdx()
            bonds[an - MOL_SPLIT_START] = b.GetBondType()
            a.SetAtomicNum(0)
            
    return join, bonds, rem
            
            
def join_fragments(fragments):
    
    to_join = []
    bonds = []
    pairs = []
    del_atoms = []
    new_mol = fragments[0]
    
    j,b,r = get_join_list(fragments[0])
    to_join += j
    del_atoms += r
    bonds += b
    offset = fragments[0].GetNumAtoms()
    
    for f in fragments[1:]:
        
        j,b,r = get_join_list(f)
        p = to_join.pop()
        pb = bonds.pop()

        # Check bond types if b[:-1] == pb
        if b[:-1] != pb:
            assert("Can't connect bonds")
        
        
        
        pairs.append((p, j[-1] + offset,pb))
        
        for x in j[:-1]:
            to_join.append(x + offset)
        for x in r:
            del_atoms.append(x + offset)
        bonds += b[:-1]
        
        offset += f.GetNumAtoms()
        new_mol = Chem.CombineMols(new_mol, f)


    new_mol =  Chem.EditableMol(new_mol)
    
    for a1,a2,b in pairs:
        new_mol.AddBond(a1,a2, order=b)
    
    # Remove atom with greatest number first:
    for s in sorted(del_atoms, reverse=True):
        new_mol.RemoveAtom(s)
    return new_mol.GetMol()
    
    
    
    


def get_class(fragment):
    
    is_ring = False
    n = 0
    
    for a in fragment.GetAtoms():
        if a.IsInRing():
            is_ring = True

        if a.GetAtomicNum() >= MOL_SPLIT_START:
            n += 1
        
    smi = Chem.MolToSmiles(fragment)

    if n == 1:
        cl = "R-group"
    elif is_ring:
        cl = "Scaffold-" + str(n)
    else:
        cl = "Linker-" + str(n)
    
    return cl



def should_use(fragment):
    
    n = 0
    m = 0
    for a in fragment.GetAtoms():
        m += 1
        if a.GetAtomicNum() >= MOL_SPLIT_START:
            n += 1
        if n > MAX_FREE or m > MAX_ATOMS:
            return False
    
    return True





def get_fragments(mols):

    used_mols = np.zeros(len(mols)) != 0

    fragments = dict()

    # Get all non-ring single bonds (including to H) and store in list (listofsinglebonds)    
    i = -1
    for mol in mols:
        i += 1
        try:
            fs = split_molecule(mol)
        except:
            logging.exception("Could not split %r", Chem.MolToSmiles(mol))
            continue

        if len(fs) <= MAX_FRAGMENTS and all(map(should_use, fs)):
            used_mols[i] = True 
        else:
            continue

        for f in fs:
            cl = get_class(f)
            fragments[Chem.MolToSmiles(f)] = (f, cl)

    return fragments, used_mols
