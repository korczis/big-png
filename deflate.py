#!/usr/bin/env python

# David Fifield <david@bamsoftware.com>
# http://www.bamsoftware.com/hacks/deflate.html
# This program is in the public domain.

import Image
import struct
import sys
import zlib

# For ZLIB and DEFLATE, see RFCs 1950 and 1951 respectively.

# An abstraction to build up byte strings from bits.
class bit_buffer (object):
    def __init__(self):
        self.clear()

    def clear(self):
        self.buf = []
        self.work = 0
        self.p = 0

    def push(self, val, nbits):
        while nbits > self.lack():
            tmp = val % (1 << self.lack())
            self.work = self.work | (tmp << self.p)
            nbits -= self.lack()
            val = val // (1 << self.lack())
            self.buf.append(self.work)
            self.work = 0
            self.p = 0
        val %= 1 << nbits;
        self.work = self.work | (val << self.p)
        self.p += nbits
        if self.lack() == 0:
            self.buf.append(self.work)
            self.work = 0
            self.p = 0

    def push_rev(self, val, nbits):
        m = (1 << nbits) >> 1
        while m > 0:
            if val & m:
                self.push(0b1, 1)
            else:
                self.push(0b0, 1)
            m >>= 1

    def lack(self):
        return 8 - self.p

    def iseven(self):
        return self.p == 0

    def getbuf(self):
        return "".join([chr(x) for x in self.buf])

# Deflate using fixed Huffman codes.
def deflate(data):
    bits = bit_buffer()

    # 0     Not final block
    bits.push(0b0, 1)
    # 01    Fixed Huffman codes
    bits.push(0b01, 2)

    for c in data:
        x = ord(c)
        if x <= 143:
            bits.push_rev(0b00110000 + x, 8)
        else:
            bits.push_rev(0b110010000 + (x - 144), 9)
    bits.push_rev(0b0000000, 7)

    # Round to a byte boundary with an uncompressed block.
    if not bits.iseven():
        bits.push(0b0, 1)
        bits.push(0b00, 2)
        while not bits.iseven():
            bits.push(0b0, 1)
        bits.push(0b00000000, 8)
        bits.push(0b00000000, 8)
        bits.push(0b11111111, 8)
        bits.push(0b11111111, 8)

    return bits.getbuf()

# For a given length, return the 3-tuple
#   (length code, extra bits, number of extra bits)
# This is based on the table in RFC 1951, section 3.2.5.
def length_code_for(n):
    if n < 3:
        return None, None, None
    if n < 11:
        baselen = 3
        basecode = 257
        nbits = 0
    elif n < 19:
        baselen = 11
        basecode = 265
        nbits = 1
    elif n < 35:
        baselen = 19
        basecode = 269
        nbits = 2
    elif n < 67:
        baselen = 35
        basecode = 273
        nbits = 3
    elif n < 131:
        baselen = 67
        basecode = 277
        nbits = 4
    elif n < 258:
        baselen = 131
        basecode = 281
        nbits = 5
    else:
        return 285, 258, 0

    m = 1 << nbits
    return (n - baselen) // m + basecode, nbits, (n - baselen) % m

# This is a specialized version of DEFLATE that can only compress strings
# containing only \x00 bytes.
#
# The return value is a 3-tuple (preamble, n, postamble). The deflated stream is
# contructed by writing the preamble, then n \x00 bytes, then the postamble.
def deflate_zeroes(n):
    # The rest of this algorithm doesn't work for 1032 bytes or less.
    if n <= 1032:
        return deflate("\x00" * n), 0, ""

    bits = bit_buffer()

    # 0     Not final block
    bits.push(0b0, 1)
    # 10    Dynamic Huffman codes
    bits.push(0b10, 2)
    # 11101 (decimal 29) 286 literal/length codes
    bits.push(0b11101, 5)
    # 00001 (decimal 1) 2 distance codes (we only use 1)
    bits.push(0b00001, 5)
    # 1110  (decimal 14) 18 code length codes (we need access to the
    #       length-1 code).
    bits.push(0b1110, 4)

    # Figure out how much is left over after compressing 258 zeroes at at time.
    # n - 1 because we must emit a literal byte first.
    num_excess = (n - 1) % 258
    excess_code, excess_nbits, excess_bits = length_code_for(num_excess)

    # The Huffman tree for code lengths. Give us code lengths for 0, 1, 2, 3,
    # and 18.
    #  00 -> 1
    #  01 -> 3
    #  10 -> 18
    # 110 -> 0
    # 111 -> 2
    bits.push(0b000, 3) # 16
    bits.push(0b000, 3) # 17
    bits.push(0b010, 3) # 18
    bits.push(0b011, 3) # 0
    bits.push(0b000, 3) # 8
    bits.push(0b000, 3) # 7
    bits.push(0b000, 3) # 9
    bits.push(0b000, 3) # 6
    bits.push(0b000, 3) # 10
    bits.push(0b000, 3) # 5
    bits.push(0b000, 3) # 11
    bits.push(0b000, 3) # 4
    bits.push(0b000, 3) # 12
    bits.push(0b010, 3) # 3
    bits.push(0b000, 3) # 13
    bits.push(0b011, 3) # 2
    bits.push(0b000, 3) # 14
    bits.push(0b010, 3) # 1

    # Now we need a literal/lengths Huffman tree with
    #   0 -> 285
    #  10 -> 0
    # 110 -> 256
    # 111 -> excess_code

    # Have to reverse the bit codes here. "Huffman codes are packed starting
    # with the most-significant bit of the code."
    bits.push_rev(0b111, 3)     # 0: code length 2
    bits.push_rev(0b10, 2)      # code length 18, extra bits to follow
    bits.push(0b1111111, 7) # 1-138: code length 0 (127 + 11 entries)
    bits.push_rev(0b10, 2)      # code length 18, extra bits to follow
    bits.push(0b1101010, 7) # 139-255: code length 0 (106 + 11 entries)
    bits.push_rev(0b01, 2)      # 256: code length 3
    if excess_code:
        if excess_code - 257 >= 11:
            bits.push_rev(0b10, 2) # code length 18, extra bits to follow
            bits.push(excess_code - 257 - 11, 7)
        else:
            for i in range(257, excess_code):
                bits.push_rev(0b110, 3) # code length 0
        bits.push_rev(0b01, 2) # excess_code: code length 3
        if 285 - (excess_code + 1) >= 11:
            bits.push_rev(0b10, 2) # code length 18, extra bits to follow
            bits.push(285 - (excess_code + 1) - 11, 7) # 18
        else:
            for i in range(excess_code + 1, 285):
                bits.push_rev(0b110, 3) # code length 0
    else:
        bits.push_rev(0b01, 2) # Insert dummy at 257 to make the tree work.
        bits.push_rev(0b10, 2) # code length 18, extra bits to follow
        bits.push(285 - 258 - 11, 7) # 18
    bits.push_rev(0b00, 2) # 285: code length 1

    # Now the distance Huffman tree. "If only one distance code is used, it is
    # encoded using one bit, not zero bits; in this case there is a single code
    # length of one, with one unused code." We store the unused code with a code
    # length of 1 instead of 0 because that's one bit shorter in the code
    # lengths tree we contstructed.
    bits.push_rev(0b00, 2) # code length 1
    bits.push_rev(0b00, 2) # code length 1

    # Write a literal \x00.
    assert n >= 1
    bits.push(0b01, 2)
    n -= 1

    # At this point our bit offset may be even or odd. Every block of 258 we
    # write takes two bytes. We want to do byte operations for most of the data.
    # Push up to an even bit offset, but remember if we have to add an extra bit
    # later.
    #
    # This is the part that doesn't work for small blocks. We may push up to 7
    # bits here, representing up to 4 * 258 = 1032 zeroes.
    odd = False
    while not bits.iseven():
        bits.push(0b0, 1)
        if not odd:
            assert n >= 258
            n -= 258
        odd = not odd

    preamble = bits.getbuf()

    num_zeroes = n // (258 * 4)
    n -= num_zeroes * (258 * 4)

    bits.clear()
    while n >= 258:
        bits.push(0b00, 2)
        n -= 258

    # Round out the odd bit if necessary.
    if odd:
        bits.push(0b0, 1)

    if num_excess < 3:
        for i in range(num_excess):
            bits.push(0b01, 2) # literal \x00
    else:
        bits.push(0b111, 3) # excess_code
        bits.push(excess_bits, excess_nbits)
        bits.push(0b0, 1) # distance 1

    n -= num_excess
    assert n == 0

    bits.push(0b011, 3) # 256, end of data

    # Round to a byte boundary with an uncompressed block.
    if not bits.iseven():
        bits.push(0b0, 1)
        bits.push(0b00, 2)
        while not bits.iseven():
            bits.push(0b0, 1)
        bits.push(0b00000000, 8)
        bits.push(0b00000000, 8)
        bits.push(0b11111111, 8)
        bits.push(0b11111111, 8)

    postamble = bits.getbuf()

    return preamble, num_zeroes, postamble

def adler32_zeroes(n, start = 1):
    s1 = (start & 0xffff) % 65521
    s2 = ((start >> 16) & 0xffff) % 65521
    return (((s2 + n * s1) % 65521) << 16) + s1

class zlib_stream (object):
    ZEROES_1024 = "\x00" * 1024

    def __init__(self):
        self.parts = []
        self.checksum = 1

    def push(self, data):
        self.checksum = zlib.adler32(data, self.checksum)
        self.parts.append(deflate(data))

    def push_zeroes(self, n):
        self.checksum = adler32_zeroes(n, self.checksum)
        self.parts.append(deflate_zeroes(n))

    def length(self):
        l = 2 # Header.
        for part in self.parts:
            if type(part) == str:
                l += len(part)
            else:
                l += len(part[0]) + part[1] + len(part[2])
        l += 5 # Final empty block.
        l += 4 # Checksum.
        return l

    def out(self):
        yield struct.pack("BB", 0b01111000, 0b11011010)
        for i in range(len(self.parts)):
            part = self.parts[i]
            final = i + 1 == len(self.parts)
            if type(part) == str:
                yield part
            else:
                preamble, n, postamble = part
                yield preamble
                while n >= 1024:
                    yield self.ZEROES_1024
                    n -= 1024
                yield "\x00" * n
                yield postamble
        yield "\x01\x00\x00\xff\xff"
        yield struct.pack(">L", self.checksum & 0xffffffff)

def test_zlib(n):
    s = zlib_stream()
    s.push_zeroes(n)
    z = "".join(s.out())
    expected = "\x00" * n
    d = zlib.decompress(z)
    print n, len(d)
    assert d == expected

def test():
    test_zlib(0)
    test_zlib(1)
    for n in range(258, 100000, 258):
        test_zlib(n - 1)
        test_zlib(n)
        test_zlib(n + 1)

# test()
# sys.exit()

# PNG code.

def chunk(type, data):
    crc = zlib.crc32(type + data) & 0xffffffff
    return struct.pack(">L", len(data)) + type + data + struct.pack(">L", crc)

def chunk_IHDR(width, height, depth, color):
    data = struct.pack(">LLBBBBB", width, height, depth, color, 0, 0, 0)
    return chunk("IHDR", data)

def chunk_PLTE(rgb):
    data = "".join(struct.pack("BBB", *x) for x in rgb)
    return chunk("PLTE", data)

secret_image = Image.open("secret.png")
secret_w, secret_h = secret_image.size
secret_p = secret_image.load()

# out = open("out.png", "w")
out = sys.stdout

width = 225000
height = 225000

# PNG header.
out.write("\x89\x50\x4e\x47\x0d\x0a\x1a\x0a")
out.write(chunk_IHDR(width, height, 1, 3))
out.write(chunk_PLTE(((0x40, 0x00, 0xe0), (0xe0, 0x00, 0x40))))

assert secret_w <= width
assert secret_h <= height

span = (width - 1) // 8 + 1

top = (height - secret_h) // 2
bottom = height - secret_h - top
left = (width - secret_w) // 2 // 8
right = span - secret_w // 8 - left

zlib_data = zlib_stream()
zlib_data.push_zeroes((1 + span) * top + 1 + left)
for i in range(secret_h):
    data = []
    for x in range(0, secret_w, 8):
        c = 0
        for j in range(8):
            c = (c << 1) | secret_p[x + j, i]
        data.append(chr(c))
    zlib_data.push("".join(data))
    if i < secret_h - 1:
        zlib_data.push_zeroes(right + 1 + left)
zlib_data.push_zeroes(right + (1 + span) * bottom)

out.write(struct.pack(">L", zlib_data.length()))
out.write("IDAT")
crc = zlib.crc32("IDAT")
for x in zlib_data.out():
    crc = zlib.crc32(x, crc)
    out.write(x)
out.write(struct.pack(">L", crc & 0xffffffff))

out.write(chunk("IEND", ""))
out.close()
