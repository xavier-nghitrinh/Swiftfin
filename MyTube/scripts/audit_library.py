import os
import sys
import json
import csv
import paramiko
from collections import defaultdict
from pathlib import Path

SSH_HOST = "192.168.1.131"
SSH_PORT = 8022
SSH_USER = "u"
SSH_PASS = "16468878"
REMOTE_MEDIA_DIR = "/storage/0692F50692F4FACF/yt_video"

REMOTE_SCRIPT = r"""
import os
import sys
import json
import glob
from collections import defaultdict
from pathlib import Path

root = '/storage/0692F50692F4FACF/yt_video'

channels = []
for entry in os.scandir(root):
    if entry.is_dir():
        channels.append(entry.name)

report = {
    "total_channels": len(channels),
    "channel_names": sorted(channels),
    "video_files": [],
    "json_files": [],
    "nfo_files": [],
    "image_files": [],
    "other_files": [],
    "subfolder_patterns": set(),
}

all_files = []
for dirpath, dirnames, filenames in os.walk(root):
    rel_dir = os.path.relpath(dirpath, root)
    if rel_dir != ".":
        parts = rel_dir.split(os.sep)
        if len(parts) > 1:
            report["subfolder_patterns"].add(parts[1])
            
    for f in filenames:
        full_path = os.path.join(dirpath, f)
        ext = os.path.splitext(f)[1].lower()
        if ext in [".mkv", ".mp4", ".webm"]:
            report["video_files"].append(full_path)
        elif ext == ".json":
            report["json_files"].append(full_path)
        elif ext == ".nfo":
            report["nfo_files"].append(full_path)
        elif ext in [".jpg", ".jpeg", ".png", ".webp"]:
            report["image_files"].append(full_path)
        else:
            report["other_files"].append(full_path)

report["subfolder_patterns"] = list(report["subfolder_patterns"])

# Check sample json
sample_json_keys = {}
sample_json_path = None
if report["json_files"]:
    sample_json_path = report["json_files"][0]
    try:
        with open(sample_json_path, 'r', encoding='utf-8') as jf:
            sample_data = json.load(jf)
            sample_json_keys = list(sample_data.keys())
            report["sample_json_snippet"] = {
                "id": sample_data.get("id"),
                "title": sample_data.get("title"),
                "channel": sample_data.get("channel"),
                "channel_id": sample_data.get("channel_id"),
                "upload_date": sample_data.get("upload_date"),
                "duration": sample_data.get("duration"),
                "webpage_url": sample_data.get("webpage_url"),
                "width": sample_data.get("width"),
                "height": sample_data.get("height"),
                "ext": sample_data.get("ext")
            }
    except Exception as e:
        report["sample_json_error"] = str(e)

# Match video and json
# For each video, see if there is matching .info.json or .json
# In ytdl-sub, video might be: "s2026.e081401 - Title.mkv"
# and json might be: "s2026.e081401 - Title.info.json" or similar
video_matches = []
matched_count = 0
missing_json_count = 0
video_ids = defaultdict(list)

for v in report["video_files"]:
    base = os.path.splitext(v)[0]
    dirn = os.path.dirname(v)
    # Check possible json names
    candidate_jsons = [
        base + ".info.json",
        base + ".json"
    ]
    found_json = None
    for c in candidate_jsons:
        if os.path.exists(c):
            found_json = c
            break
            
    v_id = None
    upload_date = None
    channel = None
    title = None
    
    if found_json:
        matched_count += 1
        try:
            with open(found_json, 'r', encoding='utf-8') as jf:
                jdata = json.load(jf)
                v_id = jdata.get("id")
                upload_date = jdata.get("upload_date")
                channel = jdata.get("channel")
                title = jdata.get("title")
        except:
            pass
    else:
        missing_json_count += 1
        
    if v_id:
        video_ids[v_id].append(v)
        
    video_matches.append({
        "video_path": v,
        "json_path": found_json,
        "video_id": v_id,
        "upload_date": upload_date,
        "channel": channel,
        "title": title
    })

duplicates = {k: v for k, v in video_ids.items() if len(v) > 1}

summary = {
    "total_channels": report["total_channels"],
    "total_video_files": len(report["video_files"]),
    "total_json_files": len(report["json_files"]),
    "total_nfo_files": len(report["nfo_files"]),
    "total_image_files": len(report["image_files"]),
    "other_files_count": len(report["other_files"]),
    "subfolder_patterns": report["subfolder_patterns"],
    "matched_video_json_count": matched_count,
    "missing_json_count": missing_json_count,
    "duplicate_video_ids_count": len(duplicates),
    "duplicate_video_ids": duplicates,
    "sample_json_snippet": report.get("sample_json_snippet"),
    "sample_json_keys": sample_json_keys[:30] if sample_json_keys else [],
}

print("AUDIT_SUMMARY_START")
print(json.dumps(summary, indent=2, ensure_ascii=False))
print("AUDIT_SUMMARY_END")

# Also dump 5 sample matched records
print("SAMPLE_MATCHES_START")
print(json.dumps(video_matches[:5], indent=2, ensure_ascii=False))
print("SAMPLE_MATCHES_END")
"""

def main():
    print(f"Connecting to {SSH_HOST}:{SSH_PORT}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=10)
    print("Running audit script remotely...")

    # Write remote script to a temp file and execute
    sftp = client.open_sftp()
    remote_script_path = "/data/data/com.termux/files/home/audit_scanner.py"
    with sftp.file(remote_script_path, "w") as f:
        f.write(REMOTE_SCRIPT)
    sftp.close()

    stdin, stdout, stderr = client.exec_command(f"python3 {remote_script_path}")
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")

    if err:
        print("Stderr:", err)

    # Clean up remote temp file
    client.exec_command(f"rm -f {remote_script_path}")
    client.close()

    # Parse output
    if "AUDIT_SUMMARY_START" in out:
        summary_raw = out.split("AUDIT_SUMMARY_START")[1].split("AUDIT_SUMMARY_END")[0].strip()
        summary = json.loads(summary_raw)
        
        output_dir = Path(r"c:\Users\nhnha\Documents\video-tools\MyTube\scripts")
        report_path = output_dir / "audit_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"Audit report saved to: {report_path}")
        print("\n--- Summary ---")
        print(f"Channels: {summary['total_channels']}")
        print(f"Videos: {summary['total_video_files']}")
        print(f"JSON metadata files: {summary['total_json_files']}")
        print(f"Matched Video + JSON: {summary['matched_video_json_count']}")
        print(f"Missing JSON: {summary['missing_json_count']}")
        print(f"Subfolder patterns: {summary['subfolder_patterns']}")
        print(f"Duplicate IDs: {summary['duplicate_video_ids_count']}")
        print("Sample JSON keys:", summary.get("sample_json_keys"))
        print("Sample JSON snippet:", json.dumps(summary.get("sample_json_snippet"), indent=2, ensure_ascii=False))
        
    if "SAMPLE_MATCHES_START" in out:
        samples_raw = out.split("SAMPLE_MATCHES_START")[1].split("SAMPLE_MATCHES_END")[0].strip()
        samples = json.loads(samples_raw)
        sample_csv_path = Path(r"c:\Users\nhnha\Documents\video-tools\MyTube\scripts\audit_sample.csv")
        with open(sample_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["video_id", "channel", "title", "upload_date", "video_path", "json_path"])
            writer.writeheader()
            for s in samples:
                writer.writerow(s)
        print(f"Sample CSV saved to: {sample_csv_path}")

if __name__ == "__main__":
    main()
