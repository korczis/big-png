# big-png

Biggest image in the smallest space

What’s the biggest pixel size of a PNG image in the smallest number of bytes? I wanted to try to create an image that could be downloaded but whose pixel buffer would be too big to store in the RAM of a PC. Here is a bzip2 file of 420 bytes that uncompresses to a PNG image of 6,132,534 bytes (5.8 MB) and 225,000 × 225,000 pixels (50.625 gigapixels), which, if represented as a pixel buffer of 3 bytes per pixel, takes about 141.4 GB.

spark.png.bz2

The program used to make it: deflate.py.

`bzr get http://www.bamsoftware.com/bzr/deflate`

PNG uses DEFLATE compression in a zlib wrapper. DEFLATE can asymptotically approach a compression ratio of 1032:1: each pair of bits can represent 258 zero bytes, and then there’s some constant overhead for headers and such.

The image is almost entirely zeroes, with a secret message in the center. We gain an extra factor of 8 pixels by using a 1-bit colorspace. Even with this maximum compression, the PNG file is basically a long string of zero bytes. bzip2 has a run-length preprocessing step that crunches these megabytes into a few hundred bytes.

## Things to try

* Upload as your profile picture to some online service, try to crash their image processing scripts.
* Set as your web site’s favicon; try to crash browsers that don’t check the size.

## Related reading

* Defending Libpng Applications Against Decompression Bombs
