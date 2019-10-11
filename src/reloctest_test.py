from    testmc.m6502 import  Machine, Registers as R, Instructions as I
import  pytest

@pytest.fixture
def M():
    M = Machine()
    M.load('.build/obj/reloctest')
    return M

def test_relocaddr(M):
    S = M.symtab
    assert 0x400 == S.reloctest
    assert 0x40D == S.ident

def test_global(M):
    s = "@[reloctest]@"
    assert s == M.str(M.symtab.reloctest, len(s))

def test_ident(M):
    S = M.symtab
    ident_str = "reloctest.a65"
    assert ident_str == M.str(S.ident, len(ident_str))
