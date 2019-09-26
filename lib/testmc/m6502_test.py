from    testmc.m6502 import  Machine, Registers as R, Instructions as I
from    testmc.asxxxx import  MemImage

from    io import  BytesIO
import  pytest

####################################################################
#   Registers

def test_Regs_cons():
    r = R(0x1234, x=0x56, C=1, I=0)
    assert r.pc == 0x1234
    assert r.a  is None
    assert r.x  == 0x56
    assert r.y  is None
    assert r.Z  == None
    assert r.C  == 1
    assert r.I  == 0

    #   Immutable
    with pytest.raises(AttributeError) as e:
        r.I = 1
    assert e.match("can't set attribute")

def test_Regs_cons_badvalue():
    with pytest.raises(ValueError) as e:
        R('hello')
    assert e.match('bad value: hello')
    with pytest.raises(ValueError) as e:
        R(-1)
    assert e.match('bad value: -1')

def test_Regs_conspsr():
    ' Construction with a program status register byte as pushed on stack. '

    with pytest.raises(AttributeError) as e:
        R(psr=0xff, V=0)
    assert e.match("must not give both psr and flag values")

    with pytest.raises(AttributeError) as e:
        R(psr=0x123)
    assert e.match('invalid psr: 0x123')

    r = R(psr=0xff)
    assert (  1,   1, 1,   1,   1,   1) \
        == (r.N, r.V, r.D, r.I, r.Z, r.C)

    r = R(psr=0)
    assert (  0,   0, 0,   0,   0,   0) \
        == (r.N, r.V, r.D, r.I, r.Z, r.C)

def test_Regs_repr_1():
    r = R(1, 2, 0xa0, sp=0xfe, psr=0b10101010)
    rs = '6502 pc=0001 a=02 x=A0 y=-- sp=FE Nv--DiZc'
    assert rs == repr(r)
    assert rs == str(r)

def test_Regs_repr_2():
    r = R(y=7, V=1, Z=0)
    rs = '6502 pc=---- a=-- x=-- y=07 sp=-- -V----z-'
    assert rs == repr(r)
    assert rs == str(r)

def test_Regs_eq_pc_only():
    assert R(1234) != 1234
    assert      1234  != R(1234)
    assert R(1234) == R(1234)
    assert R(None) == R(1234)
    assert R(1234) == R(None)
    assert R(None) == R(None)
    assert R(1234) != R(1235)

def test_Regs_eq():
    all     = R(0x1234, 0x56, 0x78, 0x9a, 0xbc, psr=0b01010101)
    again   = R(0x1234, 0x56, 0x78, 0x9a, 0xbc, psr=0b01010101)

    assert      all == all
    assert not (all != all)     # Were we seeing __ne__() delgation problems?
    assert      all == again
    assert not (all != again)

    assert all != R(0)
    assert all != R(1)
    assert all == R(0x1234)

    assert all != R(a=0)
    assert all != R(a=1)
    assert all == R(a=0x56)

    assert all != R(C=0)
    assert all == R(C=1)
    assert all == R(y=0x9a, sp=0xbc, V=1, D=0, I=1, Z=0)


####################################################################
#   Machine and loader

@pytest.fixture
def M():
    return Machine()

def test_Machine_memory_zeroed(M):
    assert [0]*0x10000 == M.mpu.memory

def test_Machine_deposit(M):
    M.deposit(6, [9, 2, 3, 8])
    assert [0]*6 + [9, 2, 3, 8] + [0]*(0x10000 - 6 - 4) == M.mpu.memory

def test_Machine_examine(M):
    M.mpu.memory[0x180:0x190] = range(0xE0, 0xF0)
    assert   0xE0 == M.byte(0x180)
    assert 0xE1E0 == M.word(0x180)
    assert   0xE8 == M.byte(0x188)
    assert 0xE9E8 == M.word(0x188)

def test_Machine_examine_stack(M):
    #   Confirm the emulator's internal format is the bottom 8 bits of the SP.
    assert 0xff == M.mpu.sp

    M.mpu.memory[0x180:0x190] = range(0xE0, 0xF0)

    M.setregs(sp=0x87)
    assert   0xE8 == M.spbyte()
    assert 0xE9E8 == M.spword()
    assert   0xEB == M.spbyte(3)
    assert 0xECEB == M.spword(3)

    M.setregs(sp=0x7F)
    assert   0xE0 == M.spbyte()
    assert 0xE1E0 == M.spword()

    M.setregs(sp=0xFE)
    assert 0 == M.spbyte()
    with pytest.raises(IndexError) as e:
        M.spword()
    assert e.match('stack underflow: addr=01FF size=2')

    with pytest.raises(IndexError): M.spbyte(1)
    with pytest.raises(IndexError): M.spword(1)
    with pytest.raises(IndexError): M.spbyte(0xFFFF)
    with pytest.raises(IndexError): M.spword(0xFFFF)

def test_Machine_str(M):
    M.deposit(0x100, [0x40, 0x41, 0x42, 0x63, 0x64])
    assert '@ABcd' == M.str(0x100, 5)
    #   Test chars with high bit set here,
    #   once we figure out how to handle them.

def test_Machine_setregs(M):
    M.setregs(y=4, a=2)
    assert  R(y=4, a=2) == M.regs

    M.mpu.p = 0b01010101
    M.setregs(0x1234, 0x56, 0x78, 0x9a, 0xbc)
    r     = R(0x1234, 0x56, 0x78, 0x9a, 0xbc, psr=0b01010101)
    assert r == M.regs

def test_Machine_step(M):
    ''' Test a little program we've hand assembled here to show
        that we're using the MPU API correctly.
    '''
    #   See py65/monitor.py for examples of how to set up and use the MPU.
    M.deposit(7, [0x7E])
    M.deposit(0x400, [
        I.LDA,  0xEE,
        I.LDXz, 0x07,
        I.NOP,
    ])
    assert   0x07 == M.byte(0x403)
    assert 0xEEA9 == M.word(0x400)  # LSB, MSB

    assert R(0, 0, 0, 0) == M.regs
    M.setregs(pc=0x400)

    M.step(); assert R(0x402, a=0xEE) == M.regs
    M.step(); assert R(0x404, x=0x7E) == M.regs
    M.step(); assert R(0x405, 0xEE, 0x7E, 0x00) == M.regs

def test_Machine_stepto(M):
    M.deposit(0x300, [I.NOP, I.LDA, 2, I.NOP, I.RTS, I.BRK])

    M.setregs(pc=0x300)
    M.stepto(I.NOP)                 # Always executes at least one instruction
    assert R(0x303) == M.regs
    assert M.mpu.processorCycles == 4

    M.setregs(pc=0x300)
    M.stepto(I.RTS)
    assert R(0x304) == M.regs

    M.setregs(pc=0x300)
    with pytest.raises(M.Timeout):
        #   0x02 is an illegal instruciton that we should never encounter.
        #   We use about 1/10 the default timeout to speed up this test,
        #   but it's still >100 ms.
        M.stepto(0x02, 10000)

def test_Machine_stepto_multi(M):
    M.deposit(0x700, [I.NOP, I.INX, I.NOP, I.INY, I.RTS, I.BRK])

    M.setregs(pc=0x700)
    M.stepto([I.INY])
    assert R(0x703) == M.regs

    M.setregs(pc=0x700)
    M.stepto((I.INY, I.INX))
    assert R(0x701) == M.regs


def test_Machine_call_rts(M):
    M.deposit(0x580, [I.RTS])
    assert R(          a=0,    x=0) == M.regs
    M.call(   0x580, R(a=0xFE, x=8))
    assert R( 0x580,   a=0xFE, x=8) == M.regs

def test_Machine_call_shallow(M):
    M.deposit(0x590, [I.INX, I.RTS])
    M.call(0x590, R(x=3))
    assert R(0x591, x=4) == M.regs

def test_Machine_call_deep(M):
    M.deposit(0x500, [I.JSR, 0x20, 0x05, I.JSR, 0x10, 0x05, I.RTS])
    M.deposit(0x510, [I.INY, I.JSR, 0x20, 0x05, I.RTS])
    M.deposit(0x520, [I.INX, I.RTS])

    M.call(  0x500, R(x=0x03, y=0x13))
    assert R(0x506,   x=0x05, y=0x14) == M.regs

def test_Machine_load_memimage(M):
    mi = MemImage()
    rec1data = (0x8a, 0x8c, 0x09, 0x04, 0x18, 0x6d, 0x09, 0x04, 0x60)
    mi.append((0x400, rec1data))
    mi.append((0x123, (0xee,)))
    mi.entrypoint = 0x0403

    expected_mem \
        = [0] * 0x123 \
        + [0xEE] \
        + [0] * (0x400 - 0x124) \
        + list(rec1data) \
        + [0] * (0x10000 - 0x400 - 9)

    M.load_memimage(mi)
    assert R(pc=0x0403)    == M.regs
    assert expected_mem    == M.mpu.memory
