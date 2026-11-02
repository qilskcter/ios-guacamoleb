#!/usr/bin/env python3
"""Convert a raw disk image to an Android sparse image (.simg).

Usage:
  img2simg.py INPUT.img OUTPUT.simg [BLOCK_SIZE]
"""

import os
import struct
import sys

SPARSE_HEADER_MAGIC = 0xed26ff3a
CHUNK_TYPE_RAW = 0xcac1
CHUNK_TYPE_FILL = 0xcac2
CHUNK_TYPE_DONT_CARE = 0xcac3


def convert(in_path, out_path, blk_sz=4096):
    file_size = os.path.getsize(in_path)
    if file_size % blk_sz != 0:
        raise ValueError(f"Input file size ({file_size}) is not a multiple of block size ({blk_sz})")

    total_blocks = file_size // blk_sz
    print(f"[*] Converting {in_path} ({file_size >> 20} MiB, {total_blocks} blocks of {blk_sz} bytes)...")

    # Read blocks and identify runs of zeros vs raw data
    chunks = []  # list of (type, block_count, data_or_fill)
    zero_block = b'\x00' * blk_sz
    step = 4096  # read 16 MiB at a time

    with open(in_path, 'rb') as f:
        curr_type = None
        curr_count = 0
        curr_data = bytearray()

        for base in range(0, total_blocks, step):
            count = min(step, total_blocks - base)
            buf = f.read(count * blk_sz)

            for i in range(count):
                blk = buf[i * blk_sz:(i + 1) * blk_sz]
                is_zero = (blk == zero_block)

                if is_zero:
                    if curr_type == CHUNK_TYPE_DONT_CARE:
                        curr_count += 1
                        if curr_count == 65535:
                            chunks.append((curr_type, curr_count, None))
                            curr_count = 0
                    else:
                        if curr_count > 0:
                            chunks.append((curr_type, curr_count, bytes(curr_data)))
                        curr_type = CHUNK_TYPE_DONT_CARE
                        curr_count = 1
                        curr_data = bytearray()
                else:
                    if curr_type == CHUNK_TYPE_RAW:
                        curr_count += 1
                        curr_data.extend(blk)
                        if curr_count == 65535:
                            chunks.append((curr_type, curr_count, bytes(curr_data)))
                            curr_count = 0
                            curr_data = bytearray()
                    else:
                        if curr_count > 0:
                            chunks.append((curr_type, curr_count, None))
                        curr_type = CHUNK_TYPE_RAW
                        curr_count = 1
                        curr_data = bytearray(blk)

        if curr_count > 0:
            if curr_type == CHUNK_TYPE_RAW:
                chunks.append((curr_type, curr_count, bytes(curr_data)))
            else:
                chunks.append((curr_type, curr_count, None))

    print(f"[*] Writing {len(chunks)} chunks to {out_path}...")
    with open(out_path, 'wb') as out:
        # File header: magic, major=1, minor=0, file_hdr_sz=28, chunk_hdr_sz=12, blk_sz, total_blks, total_chunks, crc32=0
        hdr = struct.pack('<IHHHHIIII',
                          SPARSE_HEADER_MAGIC,
                          1, 0, 28, 12,
                          blk_sz,
                          total_blocks,
                          len(chunks),
                          0)
        out.write(hdr)

        raw_blocks = 0
        dont_care_blocks = 0

        for c_type, c_blocks, c_data in chunks:
            if c_type == CHUNK_TYPE_RAW:
                raw_blocks += c_blocks
                total_sz = 12 + c_blocks * blk_sz
                out.write(struct.pack('<HHII', CHUNK_TYPE_RAW, 0, c_blocks, total_sz))
                out.write(c_data)
            elif c_type == CHUNK_TYPE_DONT_CARE:
                dont_care_blocks += c_blocks
                out.write(struct.pack('<HHII', CHUNK_TYPE_DONT_CARE, 0, c_blocks, 12))

    out_size = os.path.getsize(out_path)
    print(f"[+] Done! Sparse image: {out_size >> 20} MiB ({raw_blocks} raw blocks, {dont_care_blocks} zero blocks skipped)")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(f"Usage: {sys.argv[0]} INPUT.img OUTPUT.simg [BLOCK_SIZE]")
    bs = int(sys.argv[3]) if len(sys.argv) > 3 else 4096
    convert(sys.argv[1], sys.argv[2], bs)
