''' testmc.asxxxx - Support for ASxxx_ assembler/linker output

    .. _ASxxxx: http://shop-pdp.net/ashtml/asxdoc.htm
'''

from    collections import namedtuple as ntup
from    struct  import unpack_from
import  re

####################################################################

class MemImage(list):
    ''' A memory image, usually loaded from a linker output file,
        consisting of an entrypoint and a list of `MemRecord` data
        records, each with the memory address at which it starts.

        This is a mutable ordered collection. The records are
        not necessarily in order of address, but `sorted()` will
        return the records ordered by address.
    '''

    MemRecord = ntup('MemRecord', 'addr data')
    MemRecord.__docs__ = \
        ''' A memory record, with an int starting address and list of
            int data present at that address.
        '''

    @staticmethod
    def parse_cocobin_fromfile(path):
        with open(path, 'rb') as stream:
            return MemImage.parse_cocobin(stream)

    @staticmethod
    def parse_cocobin(bytestream):
        ''' Parse a Tandy/Radio Shack Color Computer DISK Basic
            binary file, returning a `MemImage`.

            This is the ``-t`` output format of ASlink.

            This has poor error-handling; it is intended to be used only
            on files generated by assemblers and linkers that always
            produce valid output.
        '''
        mi = MemImage()
        while True:
            buf = bytestream.read(5)
            type, len, addr = unpack_from('>BHH', buf)
            if type == 0:
                mi.append(MemImage.MemRecord(addr,
                    unpack_from('B'*len, bytestream.read(len))))
            elif type == 0xFF:
                #   len should be 0x0000, but ignore it.
                mi.entrypoint = addr
                return mi
            else:
                raise ValueError('Bad cocobin record ' \
                    'type={:02X} len={:04X} addr={:04X} at pos {}' \
                    .format(type, len, addr, pos, bytestream.tell()))

####################################################################

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
               XXX The value below is relative to the start of this area,
               which needs to be taken from the ``.map`` file. Currently
               we ignore this and produce the wrong symbol value.
               (The symbol values in the ``.map`` file are correct, but
               only global symbols are in that file, and only the first 8
               chars of the symbol name.)
            2. The symbol or label
            3. Optional ``=`` if symbol is directly assigned.
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

