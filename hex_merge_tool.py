"""
Hex File CRC Append, Merge, and Byte Insertion Tool

Steps:
1. Read CheryLitePlatformLocalization.hex, compute CRC-32 of its binary data,
   and append the CRC as 4 bytes (big-endian) at the end.
2. Merge the result from Step 1 with CheryBoot_New.hex.
3. Insert bytes 5D 5C 5B 5A at address 0x9000-0x9003 in the merged file.
4. Output the final hex file.

Uses manual Intel HEX parsing for performance (avoids slow intelhex library).
"""

import struct
import zlib

# --- Configuration ---
INPUT_LOCALIZATION = 'CheryLitePlatformLocalization.hex'
INPUT_BOOT = 'CheryBoot_New.hex'
OUTPUT_FINAL = 'output_final.hex'

# Bytes to insert at 0x9000-0x9003
INSERT_ADDRESS = 0x9000
INSERT_DATA = bytes([0x5D, 0x5C, 0x5B, 0x5A])


def parse_hex_file(filepath):
    """
    Parse an Intel HEX file into a dictionary of {absolute_address: byte_value}.
    Returns (data_dict, min_addr, max_addr, start_address_or_None)
    """
    data = {}
    current_base_addr = 0  # Base address from type 02 or type 04 records
    start_address = None
    min_addr = None
    max_addr = None

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line[0] != ':':
                continue

            byte_count = int(line[1:3], 16)
            address = int(line[3:7], 16)
            record_type = int(line[7:9], 16)

            if record_type == 0x00:
                # Data record
                abs_addr = current_base_addr | address
                for i in range(byte_count):
                    byte_val = int(line[9 + i * 2:11 + i * 2], 16)
                    addr = abs_addr + i
                    data[addr] = byte_val
                    if min_addr is None or addr < min_addr:
                        min_addr = addr
                    if max_addr is None or addr > max_addr:
                        max_addr = addr

            elif record_type == 0x01:
                # End of file
                break

            elif record_type == 0x02:
                # Extended segment address: base = segment << 4
                segment = int(line[9:13], 16)
                current_base_addr = segment << 4

            elif record_type == 0x04:
                # Extended linear address: base = value << 16
                upper = int(line[9:13], 16)
                current_base_addr = upper << 16

            elif record_type == 0x05:
                # Start address
                start_address = int(line[9:17], 16)

    return data, min_addr, max_addr, start_address


def compute_crc32(data_dict, min_addr, max_addr):
    """
    Compute CRC-32 over the binary content from min_addr to max_addr.
    Gaps are filled with 0xFF (standard Flash erased value).
    """
    size = max_addr - min_addr + 1
    binary_data = bytearray(b'\xFF' * size)
    for addr, byte_val in data_dict.items():
        binary_data[addr - min_addr] = byte_val

    crc_value = zlib.crc32(bytes(binary_data)) & 0xFFFFFFFF
    return crc_value


def append_crc_to_data(data_dict, max_addr, crc_value):
    """
    Append 4-byte big-endian CRC after max_addr.
    Returns new max_addr.
    """
    crc_bytes = struct.pack('>I', crc_value)
    next_addr = max_addr + 1
    for i, b in enumerate(crc_bytes):
        data_dict[next_addr + i] = b
    return next_addr + 3  # New max_addr


def merge_data(data1, data2):
    """
    Merge two data dicts. Returns merged dict.
    Warns on overlaps (data2 overwrites data1 on conflict).
    """
    merged = dict(data1)
    overlap_count = 0
    for addr, byte_val in data2.items():
        if addr in merged:
            overlap_count += 1
        merged[addr] = byte_val

    if overlap_count > 0:
        print(f"  WARNING: {overlap_count} overlapping addresses (second file takes precedence)")
    else:
        print("  No address overlap detected - clean merge")

    return merged


def insert_bytes(data_dict, address, data_bytes):
    """
    Insert bytes at the specified address.
    Warns if overwriting existing data.
    """
    for i, b in enumerate(data_bytes):
        addr = address + i
        if addr in data_dict:
            print(f"  WARNING: Overwriting 0x{addr:08X}: old=0x{data_dict[addr]:02X}, new=0x{b:02X}")
        data_dict[addr] = b
    return data_dict


def write_hex_file(data_dict, output_path):
    """
    Write a data dictionary to an Intel HEX file.
    Format matches T1QT_Left_All.hex:
    - 32 bytes per data record (0x20 prefix)
    - Type 02 (Extended Segment Address) for segment changes
    - No type 02 record for segment 0 (default)
    - No Start Address (type 05) record
    """
    if not data_dict:
        print("ERROR: No data to write!")
        return

    RECORD_SIZE = 32  # 32 bytes per data record

    # Sort addresses
    sorted_addrs = sorted(data_dict.keys())

    # Collect output lines
    lines = []
    current_segment = 0  # Track current segment (0 = default, no header needed)
    record_addrs = []

    def flush_record():
        nonlocal current_segment
        if not record_addrs:
            return

        first_addr = record_addrs[0]
        seg = first_addr >> 16

        # Emit type 02 record if segment changed and segment is not 0
        if seg != current_segment:
            if seg != 0:
                # Type 02: Extended Segment Address
                # Segment value = absolute_address >> 4
                seg_val = seg << 12  # e.g. seg=1 → 0x1000, base = 0x1000<<4 = 0x10000
                line = f':02000002{seg_val:04X}'
                checksum = (0x02 + 0x00 + 0x00 + 0x02 +
                            (seg_val >> 8) & 0xFF + seg_val & 0xFF)
                checksum = (~checksum + 1) & 0xFF
                lines.append(f'{line}{checksum:02X}')
            current_segment = seg

        # Emit data record
        offset = first_addr & 0xFFFF
        data_bytes = bytes(data_dict[a] for a in record_addrs)
        byte_count = len(data_bytes)
        line = f':{byte_count:02X}{offset:04X}00'
        checksum = (byte_count + ((offset >> 8) & 0xFF) + (offset & 0xFF) + 0x00)
        for b in data_bytes:
            line += f'{b:02X}'
            checksum += b
        checksum = (~checksum + 1) & 0xFF
        lines.append(f'{line}{checksum:02X}')
        record_addrs.clear()

    for addr in sorted_addrs:
        seg = addr >> 16
        offset = addr & 0xFFFF

        # Flush if: segment changed, offset not contiguous,
        # offset would wrap past 0xFFFF, or record is full
        if record_addrs:
            last_addr = record_addrs[-1]
            last_seg = last_addr >> 16
            last_offset = last_addr & 0xFFFF
            if (seg != last_seg or
                    offset != (last_offset + 1) & 0xFFFF or
                    last_offset == 0xFFFF or
                    len(record_addrs) >= RECORD_SIZE):
                flush_record()

        record_addrs.append(addr)

    flush_record()

    # Add EOF record
    lines.append(':00000001FF')

    # Write file
    with open(output_path, 'w') as f:
        for line in lines:
            f.write(line + '\n')


def verify_output(data_dict, expected_crc, crc_append_addr, log_callback=None):
    """Verify the final output file integrity."""
    log = log_callback or print
    log(f"\n[Verification]")

    # Check CRC at the end of localization data
    crc_readback = struct.pack('>I', expected_crc)
    crc_ok = True
    for i in range(4):
        addr = crc_append_addr + i
        actual = data_dict.get(addr, 0xFF)
        expected = crc_readback[i]
        status = "OK" if actual == expected else "MISMATCH"
        if actual != expected:
            crc_ok = False
        log(f"  CRC byte at 0x{addr:08X}: 0x{actual:02X} (expected 0x{expected:02X}) [{status}]")

    # Check inserted bytes
    insert_ok = True
    for i, expected_byte in enumerate(INSERT_DATA):
        addr = INSERT_ADDRESS + i
        actual = data_dict.get(addr, 0xFF)
        status = "OK" if actual == expected_byte else "MISMATCH"
        if actual != expected_byte:
            insert_ok = False
        log(f"  Byte at 0x{addr:08X}: 0x{actual:02X} (expected 0x{expected_byte:02X}) [{status}]")

    if crc_ok and insert_ok:
        log("  All verifications passed!")
    else:
        if not crc_ok:
            log("  FAILED: CRC verification failed!")
        if not insert_ok:
            log("  FAILED: Inserted bytes verification failed!")


def process(app_path, boot_path, output_path, log_callback=None):
    """
    Execute the full merge pipeline:
    1. Compute CRC-32 of app hex and append
    2. Merge with boot hex
    3. Insert marker bytes at 0x9000
    4. Write output file
    """
    log = log_callback or print

    # Step 1: Compute CRC-32 and append to app hex
    log(f"[Step 1] Reading {app_path} ...")
    data_loc, min_loc, max_loc, _ = parse_hex_file(app_path)
    log(f"  Address range: 0x{min_loc:08X} - 0x{max_loc:08X}")
    log(f"  Data points: {len(data_loc)}")

    log("  Computing CRC-32 ...")
    crc_value = compute_crc32(data_loc, min_loc, max_loc)
    log(f"  CRC-32: 0x{crc_value:08X}")

    crc_bytes = struct.pack('>I', crc_value)
    log(f"  CRC bytes (big-endian): {' '.join(f'{b:02X}' for b in crc_bytes)}")

    new_max = append_crc_to_data(data_loc, max_loc, crc_value)
    log(f"  CRC appended at address 0x{max_loc + 1:08X} - 0x{new_max:08X}")

    # Step 2: Merge app (with CRC) and boot hex files
    log(f"\n[Step 2] Reading {boot_path} ...")
    data_boot, min_boot, max_boot, _ = parse_hex_file(boot_path)
    log(f"  Boot address range: 0x{min_boot:08X} - 0x{max_boot:08X}")
    log(f"  Boot data points: {len(data_boot)}")
    log(f"  App address range: 0x{min_loc:08X} - 0x{new_max:08X}")

    log("  Merging ...")
    data_merged = merge_data(data_loc, data_boot)

    all_min = min(min_loc, min_boot)
    all_max = max(new_max, max_boot)
    log(f"  Merged address range: 0x{all_min:08X} - 0x{all_max:08X}")

    # Step 3: Insert marker bytes at 0x9000-0x9003
    log(f"\n[Step 3] Inserting bytes at 0x{INSERT_ADDRESS:08X} - "
        f"0x{INSERT_ADDRESS + len(INSERT_DATA) - 1:08X}")
    log(f"  Data: {' '.join(f'{b:02X}' for b in INSERT_DATA)}")
    insert_bytes(data_merged, INSERT_ADDRESS, INSERT_DATA)

    # Write output file
    log(f"\n[Output] Writing to {output_path} ...")
    write_hex_file(data_merged, output_path)
    log(f"  File written successfully!")

    # Verify
    verify_output(data_merged, crc_value, max_loc + 1, log_callback=log)

    log(f"\nDone! Final output: {output_path}")


if __name__ == '__main__':
    process(INPUT_LOCALIZATION, INPUT_BOOT, OUTPUT_FINAL)
