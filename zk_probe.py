"""
Realtime / ZKTeco device capability probe.

Usage:
    python zk_probe.py <device-ip> [port] [comm-password]

Example:
    python zk_probe.py 192.168.1.201
    python zk_probe.py 192.168.1.201 4370 0

Run this on the Windows PC that runs the Puller, on the same LAN as the device.
It only READS from the device. It does not clear attendance, change settings,
or write anything.
"""
import sys
import traceback

from zk import ZK, const
from zk.exception import ZKErrorResponse


def hr(title):
    print("\n" + "=" * 62)
    print(title)
    print("=" * 62)


def probe(ip, port, password):
    results = {}

    for label, kwargs in (
        ("TCP", dict(force_udp=False)),
        ("UDP", dict(force_udp=True)),
    ):
        hr(f"Transport: {label}")
        conn = None
        zk = ZK(ip, port=port, timeout=30, password=password,
                ommit_ping=True, verbose=False, **kwargs)
        try:
            conn = zk.connect()
            print(f"  connect .................. OK")

            try:
                print(f"  firmware ................. {conn.get_firmware_version()}")
                print(f"  serial ................... {conn.get_serialnumber()}")
                print(f"  device name .............. {conn.get_device_name()}")
                print(f"  platform ................. {conn.get_platform()}")
            except Exception as e:
                print(f"  device info .............. FAILED ({e})")

            # Sizes tell us how many records the device thinks it holds.
            try:
                conn.read_sizes()
                print(f"  users .................... {conn.users}")
                print(f"  attendance records ....... {conn.records}")
            except Exception as e:
                print(f"  read_sizes ............... FAILED ({e})")

            # Users normally use the same buffered read as attendance,
            # so this is a useful second data point.
            try:
                users = conn.get_users()
                print(f"  get_users() .............. OK ({len(users)} returned)")
                results[f"{label}:users"] = True
            except Exception as e:
                print(f"  get_users() .............. FAILED ({type(e).__name__}: {e})")
                results[f"{label}:users"] = False

            # The actual failing call. disable_device() first is the
            # documented-correct sequence and rules out "punch during read".
            try:
                conn.disable_device()
                print(f"  disable_device() ......... OK")
            except Exception as e:
                print(f"  disable_device() ......... FAILED ({e})")

            try:
                logs = conn.get_attendance()
                print(f"  get_attendance() ......... OK ({len(logs)} records)")
                if logs:
                    print(f"    newest: {logs[-1]}")
                results[f"{label}:attendance"] = True
            except ZKErrorResponse as e:
                print(f"  get_attendance() ......... FAILED ({e})")
                results[f"{label}:attendance"] = False

                # Retry once after dropping the half-prepared buffer.
                try:
                    conn.free_data()
                    logs = conn.get_attendance()
                    print(f"  retry after free_data() .. OK ({len(logs)} records)")
                    results[f"{label}:attendance-retry"] = True
                except Exception as e2:
                    print(f"  retry after free_data() .. FAILED ({e2})")
                    results[f"{label}:attendance-retry"] = False

            try:
                conn.enable_device()
            except Exception:
                pass

        except Exception as e:
            print(f"  connect .................. FAILED ({type(e).__name__}: {e})")
            results[f"{label}:connect"] = False
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    hr("SUMMARY")
    for k, v in results.items():
        print(f"  {k:32s} {'OK' if v else 'FAILED'}")
    print("""
How to read this:

  * Any row ending ':attendance' is OK
      -> use that transport. Fix is a one-line change in the Puller.

  * 'users' OK but 'attendance' FAILED on both transports
      -> the buffered read works in general but not for the attendance
         log. Needs the legacy CMD_ATTLOG_RRQ fallback (route 1).

  * Both 'users' and 'attendance' FAILED on both transports
      -> this firmware does not serve buffered reads at all.
         Use the vendor COM SDK (route 2) or move to ADMS push (route 3).

  * 'retry after free_data()' OK where the first attempt FAILED
      -> a stale buffer was the cause. Fix is retry logic in the Puller.
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ip = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 4370
    password = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    print(f"Probing {ip}:{port} (comm password {password})")
    try:
        probe(ip, port, password)
    except Exception:
        traceback.print_exc()
