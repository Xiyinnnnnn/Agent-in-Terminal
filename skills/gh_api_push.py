import base64, json, os, re, sys, urllib.request, urllib.error
from pathlib import Path

HOME = Path.home()
TOK = re.search(r"github_pat_[A-Za-z0-9_]+",
                (HOME/".config/term_agent/memory/Agent-in-Terminal云端同步.md").read_text()).group(0)
API = "https://api.github.com/repos/Xiyinnnnnn/Agent-in-Terminal"
# FILES/DROP/MSG 每次任务改；指向 ~/.cache/cloud_* 时中转文件要留到推完
SK = HOME/".config/term_agent/skill"
FILES = [
    ("skills/00-疑难升级-大模型一次性诊断.md", SK/"00-疑难升级-大模型一次性诊断.md"),
    ("skills/00-索引.md", HOME/".cache/cloud_索引.md"),
    ("skills/.manifest", HOME/".cache/cloud_manifest"),
]
DROP = ["skills/00-疑难问题诊断-模型升级.md"]
MSG = "改名：00-疑难问题诊断-模型升级 → 00-疑难升级-大模型一次性诊断；STATE 加 GATE、流程第 1 步加本地先查"

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOK)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("User-Agent", "termux-taskwatch")
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=40) as f:
            return json.load(f)
    except urllib.error.HTTPError as e:
        print("HTTP %d %s" % (e.code, e.read()[:400].decode("utf-8", "ignore")), file=sys.stderr)
        sys.exit(1)

ref = req("GET", "/git/ref/heads/main")
base = ref["object"]["sha"]
tree = req("GET", "/git/commits/" + base)["tree"]["sha"]
print("base_commit=%s base_tree=%s" % (base[:8], tree[:8]))

entries = []
for path, local in FILES:
    blob = req("POST", "/git/blobs", {
        "content": base64.b64encode(local.read_bytes()).decode(),
        "encoding": "base64"})
    entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    print("blob %-32s %s  %d B" % (path, blob["sha"][:8], local.stat().st_size))

for path in DROP:
    entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
    print("drop %s" % path)

newtree = req("POST", "/git/trees", {"base_tree": tree, "tree": entries})["sha"]
print("new_tree=%s" % newtree[:8])
commit = req("POST", "/git/commits", {"message": MSG, "tree": newtree, "parents": [base]})
print("new_commit=%s" % commit["sha"][:8])
upd = req("PATCH", "/git/refs/heads/main", {"sha": commit["sha"], "force": False})
print("ref_updated=%s now=%s" % (bool(upd.get("object")), upd["object"]["sha"][:8]))
