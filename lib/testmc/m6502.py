''' testmc.m6502 - test framework for 6502 microcomputer code

    This uses the py65 emulator to emulate a 6502 microcomputer system.
'''

from    collections  import namedtuple
from    collections.abc   import Container
from    itertools  import repeat
from    struct  import unpack_from
from    py65.devices.mpu6502  import MPU
import  re

__all__ = ['Registers', 'Machine']

RegistersTuple = namedtuple('RegistersTuple', 'pc a x y sp N V D I Z C')
class Registers(RegistersTuple):
    ''' The register set, including flags, of the 6502.

        Any values set to `None` will be ignored in comparisons
        between two register sets.

        Register names are lower-case; flags are upper-case. The
        registers in the constructor are given in order of
        approximately how likely you are to want to check them for
        comparisons. The flags given in the program status register
        order (MSB first); you will almost invariably want to set
        those by name, or by instead passing in a program status
        register value `psr`.

        repr() returns the processor name, register values in
        hexadecimal and a flags list with the flag letter upper-case
        if set, lower-case if clear. Any values that are `None`
        (ignored in comparisons) will be printed with hyphens. repr()
        is overridden instead of just str() because pytest prints
        repr() output, and that's where we want easily to see what's
        wrong.

        This inherits from `tuple` for immutability.
    '''

    def __new__(cls,
            pc=None, a=None, x=None, y=None, sp=None,
            N=None, V=None, D=None, I=None, Z=None, C=None,
            psr=None):

        def checkvalue(n):
            try:
                if n is None or n >= 0: return
            except TypeError:
                pass
            raise ValueError('bad value: {}'.format(n))
        [ checkvalue(n) for n in [pc, a, x, y, sp, N, V, D, I, Z, C, psr] ]

        if psr is not None:
            if psr < 0 or psr > 0xff:
                raise AttributeError('invalid psr: ' + hex(psr))
            if [f for f in [Z, C, N, V, I, D] if f is not None]:
                raise AttributeError("must not give both psr and flag values")
            C = 1 if psr & 0x01 else 0
            Z = 1 if psr & 0x02 else 0
            I = 1 if psr & 0x04 else 0
            D = 1 if psr & 0x08 else 0
            V = 1 if psr & 0x40 else 0
            N = 1 if psr & 0x80 else 0

        self = super(Registers, cls) \
            .__new__(cls, pc, a, x, y, sp, N, V, D, I, Z, C)
        return self

    def __repr__(self):
        pc = '----' if self.pc is None else '{:04X}'.format(self.pc)
        a  =   '--' if self.a  is None else '{:02X}'.format(self.a )
        x  =   '--' if self.x  is None else '{:02X}'.format(self.x )
        y  =   '--' if self.y  is None else '{:02X}'.format(self.y )
        sp =   '--' if self.sp is None else '{:02X}'.format(self.sp)
        def f(char, val):   # flag letter and value
            if val is None: return '-'
            if val is 0:    return char.lower()
            if val is 1:    return char.upper()
            return '?'
        return '6502 pc={} a={} x={} y={} sp={} {}{}--{}{}{}{}' \
            .format(pc, a, x, y, sp,
                f('N', self.N), f('V', self.V),
                f('D', self.D), f('I', self.I), f('Z', self.Z), f('C', self.C))

    def __ne__(a, b):
        #   Not sure if I'm seeing problems w/the default version
        #   delegating to __eq__, but this should definitely fix it.
        return not a.__eq__(b)

    def __eq__(a, b):
        if type(a) != type(b): return False

        #print('a:', a, '\nb:', b)
        def comp(a, b): # Should we compare a and b?
            #print('comp({}, {}) → {})'.format(a, b, a is not None and b is not None))
            return a is not None and b is not None

        if comp(a.pc, b.pc) and a.pc != b.pc: return False
        if comp(a.a , b.a ) and a.a  != b.a : return False
        if comp(a.x , b.x ) and a.x  != b.x : return False
        if comp(a.y , b.y ) and a.y  != b.y : return False
        if comp(a.sp, b.sp) and a.sp != b.sp: return False
        if comp(a.V , b.V ) and a.V  != b.V : return False
        if comp(a.D , b.D ) and a.D  != b.D : return False
        if comp(a.I , b.I ) and a.I  != b.I : return False
        if comp(a.Z , b.Z ) and a.Z  != b.Z : return False
        if comp(a.C , b.C ) and a.C  != b.C : return False

        return True

class Machine():

    class Timeout(RuntimeError):
        ' The emulator ran longer than requested. '
        pass

    def __init__(self):
        self.mpu = MPU()
        self.symtab = dict()

    @property
    def regs(self):
        m = self.mpu
        return Registers(m.pc, m.a, m.x, m.y, m.sp, psr=m.p)

    def setregs(self, pc=None, a=None, x=None, y=None, sp=None):
        m = self.mpu
        if pc is not None:  m.pc = pc
        if  a is not None:   m.a =  a
        if  x is not None:   m.x =  x
        if  y is not None:   m.y =  y
        if sp is not None:  m.sp = sp
        #   We don't do processor status register here as flags should
        #   be set/reset individually, particularly because we should
        #   avoid ever changing unused bits 5 and 6.

    #   XXX This "examine" interface isn't so nice. Perhaps we can condense
    #   in down to a single examine() function that takes a length and type?

    def byte(self, addr):
        ' Examine a byte from memory. '
        return self.mpu.ByteAt(addr)

    def word(self, addr):
        ''' Examine a word from memory.
            Native endianness NESS is decoded to give a 16-bit int.
        '''
        return self.mpu.WordAt(addr)

    def _stackaddr(self, depth, size):
        addr = 0x100 + self.mpu.sp + 1 + depth
        if addr >= 0x201 - size:
            raise IndexError("stack underflow: addr={:04X} size={}" \
                .format(addr, size))
        return addr

    def spbyte(self, depth=0):
        return self.byte(self._stackaddr(depth, 1))

    def spword(self, depth=0):
        return self.word(self._stackaddr(depth, 2))

    def str(self, addr, len):
        ' Examine a string from memory. '
        #   This currently throws an exception if any of the bytes
        #   in the memory range are >0x7f. It's not clear how we
        #   should be decoding those. Possibly we want an option to
        #   clear the high bit on all chars before decoding.
        return bytes(self.mpu.memory[addr:addr+len]).decode('ASCII')

    def deposit(self, addr, values):
        self.mpu.memory[addr:addr+len(values)] = values

    def load(self, path):
        ''' Load the given ``.bin`` file and, if available, the
            symbols from a ``.rst`` (ASxxxx linker listing file)
            in the same directory.
        '''
        with open(path + '.bin', 'rb') as f:
            self.load_bin(f.read())
        try:
            with open(path + '.rst', 'r') as f:
                self.load_sym(f)
        except FileNotFoundError:
            pass

    def load_bin(self, buf):
        recs = ParseBin(buf)
        for addr, data in recs:
            self.deposit(addr, data)
        self.mpu.pc = recs.entrypoint

    def load_sym(self, f):
        self.symtab = SymTab(f)

    def step(self, count=1):
        for _ in repeat(None, count):
            self.mpu.step()

    def stepto(self, instrs, maxinstrs=100000):
        if not isinstance(instrs, Container):
            instrs = (instrs,)
        self.step()
        count = maxinstrs - 1
        while self.byte(self.mpu.pc) not in instrs:
            self.step()
            count -= 1
            if count <= 0:
                raise self.Timeout(
                    'Timeout after {} instructions'.format(maxinstrs))

    #   XXX Should also check for stack overflows in all of the above.

class ParseBin(list):
    ''' Parse records in "Tandy CoCo Disk BASIC binary" (.bin) format
        as generated by the ASxxxx assembler's `aslink` program.

        This has poor error-handling; it is intended to be used only
        on files generated by assemblers and linkers that always
        produce valid output.
    '''
    def __init__(self, buf):
        #   There's not really any reason to keep the buf here, actually,
        #   so it would be more efficient to change this to use a binary
        #   input stream.
        self.buf = buf
        pos = 0
        while True:
            type, len, addr = unpack_from('>BHH', buf, pos)
            if type == 0:
                pos += 5
                data = unpack_from('B'*len, buf, pos)
                pos += len
                self.append((addr, list(data)))
            elif type == 0xFF:
                self.entrypoint = addr
                break
            else:
                raise ValueError('Bad .bin record type {} at {}: {}' \
                    .format(type, pos, buf[pos:pos+5]))

class SymTab(dict):
    ''' The symbol table of a module, including local symbols.

        We generate this from a listing file because the other files
        (.map and debugger info) include only the global symbols that
        are exported by the module.
    '''

    def __init__(self, listing):
        super()
        if not listing: return

        #   XXX We should probably check a header line to ensure we're
        #   in 'Hexadecimal [16-bits]' mode.
        symlines = self.readsymlines(listing)
        symentries = [ entry
                       for symline in symlines if symline.strip()
                       for entry in self.splitentries(symline)
                     ]
        for e in symentries:
            name, addr = self.parseent(e)
            #   XXX deal with exceptions here?
            self[name] = addr

    @staticmethod
    def readsymlines(f):
        symlines = []
        headerline = re.compile(r'.?ASxxxx Assembler')
        while True:
            line = f.readline()
            if line == '': return                       # EOF
            if line.strip() == 'Symbol Table': break    # Reached Symbol Table
        while True:
            line = f.readline()
            if line == '': break                        # EOF
            if line.strip() == 'Area Table': break      # End of Symbol Table
            if headerline.match(line):
                f.readline()                    # 2nd header line
            else:
                symlines.append(line)
        return symlines

    @staticmethod
    def splitentries(symline):
        return [ line.strip()
                 for line in symline.split('|')
                 if line.strip() != '' ]

    @staticmethod
    def parseent(ent):
        ''' Parse the entry for a symbol from ASxxxx symbol table listing.

            Per §1.3.2, symbols consist of alphanumerics and ``$._``
            only, and may not start with a number. (Reusable symbols
            can start with a number, but they do not appear in the
            symbol table.)

            Per §1.8, the entry in the listing file is:
            1. Program  area  number (none if absolute value or external).
            2. The symbol or label
            3. Optional ``=`` if symbol is diretly assigned.
            4. Value in base of the listing or ``****`` if undefined.
            5. Zero or more of ``GLRX`` for global, local, relocatable
               and external symbols.

            Docs at <http://shop-pdp.net/ashtml/asmlnk.htm>.
        '''
        SYMENTRY = re.compile(r'(\d* )?([A-Za-z0-9$._]*) *=? * ([0-9A-F*]*)')
        match = SYMENTRY.match(ent)
        return match.group(2), int(match.group(3), 16)

    def __getattr__(self, name):
        ''' Allow reading keys as attributes, so long as they do not
            collide with existing attributes.
        '''
        if name in self:
            return self[name]
        else:
            raise AttributeError("No such attribute: " + name)

class Instructions():
    ''' Opcode constants for the 6502, named after the assembly
        instructions.

        There are often multiple opcodes per instruction, one for each
        of the different addressing modes. We distinguish these with a
        lower-case suffix:

                             implied
                  #nn        immediate
            z     nn         zero page
            zx    nn,X       zero indexed by X
            zy    nn,Y       zero indexed by Y
            a     addr       absolute (extended)
            ax    addr,X     absolute,X
            ay    addr,Y     absolute,Y
            i     [addr]     indirect
            ix    [addr,X]   indexed indirect
            iy    [addr],Y   indirect indexed


        One day we might find it worthwhile to have an Assembler class
        that can itself determine correct addressing modes and whatnot
        when assembling instructions, but there doesn't seem to be any
        gain from that at the moment.
    '''

    BRK     = 0x00
    JSR     = 0x20
    RTS     = 0x60
    LDXz    = 0xA6
    LDA     = 0xA9
    INY     = 0xC8
    INX     = 0xE8
    NOP     = 0xEA
