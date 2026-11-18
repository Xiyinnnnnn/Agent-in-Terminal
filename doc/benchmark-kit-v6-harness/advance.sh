#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
NODE=vendor/bin/node-run
STATE=.cp_state
DONE=0; [ -f "$STATE" ] && DONE=$(cat "$STATE")
SEED="$(cat .bench/seed.txt 2>/dev/null || true)"
MPATH="$PWD/.fault-path:$PATH"
masked_node() { PATH="$MPATH" "$NODE" "$@"; }
fail() { echo "cp$1 FAIL: $2" >&2; exit 1; }
ensure_faultpath() {
  if [ ! -x .fault-path/node ]; then
    mkdir -p .fault-path
    printf '#!/bin/sh\necho "node: command not found" >&2\nexit 127\n' > .fault-path/node
    chmod +x .fault-path/node
  fi
}

check1() {
  [ -f cp1_env.json ] || fail 1 "缺 cp1_env.json"
  [ -n "$SEED" ] || fail 1 "缺 .bench/seed.txt"
  "$NODE" -e '
const fs=require("fs");
const seed=fs.readFileSync(".bench/seed.txt","utf8").trim();
const d=JSON.parse(fs.readFileSync("cp1_env.json","utf8"));
for(const k of ["node","python","ffmpeg"]){
  if(typeof d[k]!=="string"||!d[k].trim()){console.error("字段 "+k+" 为空");process.exit(1);}
}
if(String(d.seed||"").trim()!==seed){console.error("seed 与 .bench/seed.txt 不一致");process.exit(1);}
if(typeof d.host!=="string"||!d.host.trim()){console.error("host 为空");process.exit(1);}
' || fail 1 "字段/seed/host 校验未过"
}

check2() {
  [ -f stage1/report/report.js ] || fail 2 "缺 stage1/report/report.js"
  grep -q "getUTC" stage1/report/report.js || fail 2 "未改用 UTC getter"
  grep -Eq "\.get(FullYear|Month|Date|Hours|Minutes|Seconds)\(" stage1/report/report.js \
    && fail 2 "仍有本地时区 getter"
  grep -q "getUTCFullYear" stage1/report/report.js || fail 2 "缺 getUTCFullYear"
  grep -q "module.exports" stage1/report/report.js || fail 2 "导出被破坏"
  bash tests/check_p1.sh >/dev/null 2>&1 || fail 2 "四时区未全绿"
}

check3() {
  [ -f cp3_plan.json ] || fail 3 "缺 cp3_plan.json"
  "$NODE" -e '
const fs=require("fs");
const d=JSON.parse(fs.readFileSync("cp3_plan.json","utf8"));
const items=d.items||[];
if(items.length<5){console.error("items 少于 5 项");process.exit(1);}
for(const it of items){
  for(const k of ["file","change","reason","evidence"]){
    if(typeof it[k]!=="string"||!it[k].trim()){console.error("缺字段 "+k);process.exit(1);}
  }
  const m=/^(.+):(\d+)$/.exec(it.evidence.trim());
  if(!m){console.error("evidence 非 路径:行号 -> "+it.evidence);process.exit(1);}
  const p=m[1];
  if(!fs.existsSync(p)){console.error("evidence 路径不存在 -> "+p);process.exit(1);}
  const n=fs.readFileSync(p,"utf8").split("\n").length;
  if(parseInt(m[2],10)>n){console.error("evidence 行号越界 -> "+it.evidence);process.exit(1);}
}
' || fail 3 "迁移清单不达标"
}

check4() {
  [ -f cp4_contract.json ] || fail 4 "缺 cp4_contract.json"
  "$NODE" -e '
const fs=require("fs");
const d=JSON.parse(fs.readFileSync("cp4_contract.json","utf8"));
const k=String(d.dedupe_key||"");
if(!/ts/.test(k)||!/level/.test(k)||!/msg/.test(k)){console.error("dedupe_key 未同时体现 ts/level/msg -> "+k);process.exit(1);}
if(!/seq/.test(String(d.tie_break||""))){console.error("tie_break 未体现 seq");process.exit(1);}
const e=Array.isArray(d.escape)?d.escape:[];
if(e.length<4){console.error("escape 至少 4 项（反斜杠/换行/回车/制表符）");process.exit(1);}
const joined=e.join("");
if(!joined.includes(String.fromCharCode(92))){console.error("escape 缺反斜杠项");process.exit(1);}
for(const ch of ["n","r","t"]){ if(!joined.includes(ch)){console.error("escape 缺 "+ch);process.exit(1);} }
if(d.tolerate_extra_fields!==true){console.error("tolerate_extra_fields 必须为 true");process.exit(1);}
if(d.stdout_clean!==true){console.error("stdout_clean 必须为 true");process.exit(1);}
' || fail 4 "数据契约不达标"
}

check5() {
  [ -f stage1/report/records.json ] || fail 5 "缺 stage1/report/records.json"
  a="$("$NODE" vendor/tools/gen_records.js "$SEED" 200 | sha256sum | cut -d' ' -f1)"
  b="$(sha256sum stage1/report/records.json | cut -d' ' -f1)"
  [ -n "$a" ] && [ "$a" = "$b" ] || fail 5 "records 与种子生成器输出不一致（须逐字节相同）"
  "$NODE" -e '
const fs=require("fs");
const d=JSON.parse(fs.readFileSync("stage1/report/records.json","utf8"));
if(!Array.isArray(d)||d.length<200){console.error("条数不足 200");process.exit(1);}
' || fail 5 "records 条数不足"
}

check6() {
  ensure_faultpath
  [ -f dist/report.js ] || fail 6 "缺 dist/report.js"
  a="$(masked_node dist/report.js 2>/dev/null | sha256sum | cut -d' ' -f1)"
  b="$(masked_node stage1/report/index.js 2>/dev/null | sha256sum | cut -d' ' -f1)"
  [ -n "$a" ] && [ "$a" = "$b" ] || fail 6 "dist 输出与 stage1 不一致（node 已被遮蔽）"
}

check7() {
  [ -f cp7_test.log ] || fail 7 "缺 cp7_test.log"
  for tz in UTC Asia/Shanghai Asia/Kolkata America/New_York; do
    grep -q "p1 ok TZ=$tz" cp7_test.log || fail 7 "缺 $tz 的 p1 ok"
  done
  [ "$(grep -c 'p1 ok TZ=' cp7_test.log)" -ge 4 ] || fail 7 "自测行不足 4 条"
}

check8() {
  ensure_faultpath
  [ -f cp8_idem.json ] || fail 8 "缺 cp8_idem.json"
  a="$(masked_node stage1/report/index.js 2>/dev/null | sha256sum | cut -d' ' -f1)"
  b="$(masked_node stage1/report/index.js 2>/dev/null | sha256sum | cut -d' ' -f1)"
  [ -n "$a" ] && [ "$a" = "$b" ] || fail 8 "两次运行 stdout 不同"
  "$NODE" -e '
const fs=require("fs");
const d=JSON.parse(fs.readFileSync("cp8_idem.json","utf8"));
if(d.runs!==2){console.error("runs 须为 2");process.exit(1);}
if(d.equal!==true){console.error("equal 须为 true");process.exit(1);}
if(d.tmp_left!==0){console.error("tmp_left 须为 0");process.exit(1);}
if(!/^[0-9a-f]{64}$/.test(String(d.stdout_sha256||""))){console.error("stdout_sha256 非法");process.exit(1);}
if(String(d.stdout_sha256)!==process.argv[1]){console.error("stdout_sha256 与实测不一致");process.exit(1);}
' "$a" || fail 8 "幂等证据不达标"
}

check9() {
  ensure_faultpath
  [ -f tasks/pipeline.sh ] || fail 9 "缺 tasks/pipeline.sh"
  [ -f cp9_resume.json ] || fail 9 "缺 cp9_resume.json"
  W="$(mktemp -d "${TMPDIR:-$HOME/.cache}/cp9.XXXXXX")" || fail 9 "mktemp 失败"
  cp -r "$PWD"/. "$W"/ || fail 9 "复制失败"
  (
    cd "$W" || exit 1
    printf '{"generated_at":"crash","entries":[{"file":"stage1/report/rep' > stage1/lock.json
    PATH="$W/.fault-path:$PATH" bash tasks/pipeline.sh > o1.txt 2>&1 || { echo "首次运行失败"; exit 1; }
    PATH="$W/.fault-path:$PATH" bash tasks/pipeline.sh > o2.txt 2>&1 || { echo "二次运行失败"; exit 1; }
    "$NODE" -e '
const fs=require("fs"),crypto=require("crypto");
const d=JSON.parse(fs.readFileSync("stage1/lock.json","utf8"));
const es=Array.isArray(d.entries)?d.entries:[];
if(es.length<3){console.error("lock entries 太少，未重建");process.exit(1);}
for(const f of fs.readdirSync("stage1/report")){
  const p="stage1/report/"+f;
  if(!fs.statSync(p).isFile()) continue;
  const h=crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
  const hit=es.find(e=>String(e.file||"")===p);
  if(!hit||String(hit.sha256)!==h){console.error("lock 未按内容重建: "+p);process.exit(1);}
}
' || exit 1
    n="$(grep -c skip o2.txt || true)"
    [ "${n:-0}" -ge 3 ] || { echo "二次运行 skip=${n:-0} < 3"; exit 1; }
  ) || fail 9 "断电后未能按内容重建并续跑"
  "$NODE" -e '
const fs=require("fs");
const d=JSON.parse(fs.readFileSync("cp9_resume.json","utf8"));
if(!(Number(d.skip)>=3)){console.error("skip 须 >=3");process.exit(1);}
if(!d.killed_at){console.error("缺 killed_at");process.exit(1);}
if(!/^[0-9a-f]{64}$/.test(String(d.rebuilt||""))){console.error("rebuilt 须为 64 位 sha256");process.exit(1);}
' || fail 9 "cp9_resume.json 不达标"
}

check10() {
  [ -f dist/report.tar.gz ] || fail 10 "缺 dist/report.tar.gz"
  [ -f cp10_pack.json ] || fail 10 "缺 cp10_pack.json"
  for f in report.js config.json records.json lock.json; do
    tar -tzf dist/report.tar.gz | grep -qx "$f" || fail 10 "包内缺 $f"
  done
  tmp="$(mktemp -d)" || fail 10 "mktemp 失败"
  tar -xzf dist/report.tar.gz -C "$tmp" || { rm -rf "$tmp"; fail 10 "解包失败"; }
  "$NODE" -e '
const fs=require("fs"),crypto=require("crypto"),path=require("path");
const dir=process.argv[1];
const d=JSON.parse(fs.readFileSync("cp10_pack.json","utf8"));
const arr=Array.isArray(d)?d:(d.files||[]);
if(arr.length<4){console.error("cp10_pack.json 条目不足");process.exit(1);}
for(const it of arr){
  const rel=String(it.path||it.file||"");
  const p=path.join(dir,rel);
  if(!fs.existsSync(p)){console.error("包内缺 "+rel);process.exit(1);}
  const h=crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
  if(h!==String(it.sha256)){console.error("sha256 不符 "+rel);process.exit(1);}
}
' "$tmp" || { rm -rf "$tmp"; fail 10 "打包清单与包内文件不符"; }
  rm -rf "$tmp"
}

check11() {
  ensure_faultpath
  [ -f cp11_install.json ] || fail 11 "缺 cp11_install.json"
  [ -d clean ] || fail 11 "缺 clean/ 目录"
  entry="$("$NODE" -e 'const d=JSON.parse(require("fs").readFileSync("cp11_install.json","utf8"));process.stdout.write(String(d.entry||""))')"
  [ -n "$entry" ] || fail 11 "cp11_install.json 缺 entry"
  [ -f "$entry" ] || fail 11 "entry 不存在: $entry"
  outf="$(mktemp)" || fail 11 "mktemp 失败"
  masked_node "$entry" >"$outf" 2>/dev/null; rc=$?
  h="$(sha256sum "$outf" | cut -d' ' -f1)"
  rm -f "$outf"
  [ "$rc" -eq 0 ] || fail 11 "clean 入口运行 rc=$rc"
  "$NODE" -e '
const fs=require("fs");
const d=JSON.parse(fs.readFileSync("cp11_install.json","utf8"));
const i=JSON.parse(fs.readFileSync("cp8_idem.json","utf8"));
if(d.rc!==0){console.error("rc 须为 0");process.exit(1);}
if(!/^[0-9a-f]{64}$/.test(String(d.stdout_sha256||""))){console.error("stdout_sha256 非法");process.exit(1);}
if(String(d.stdout_sha256)!==String(i.stdout_sha256)){console.error("stdout_sha256 与 cp8 不一致");process.exit(1);}
if(String(d.stdout_sha256)!==process.argv[1]){console.error("stdout_sha256 与 clean 实测不一致");process.exit(1);}
' "$h" || fail 11 "干净安装证据不达标"
}

check12() {
  ensure_faultpath
  [ -f cp12_audit.json ] || fail 12 "缺 cp12_audit.json"
  [ -f .bench/baseline.sha256 ] || fail 12 "缺素材哈希基线"
  sha256sum -c .bench/baseline.sha256 >/dev/null 2>&1 || fail 12 "素材被改（tests/SPEC/vendor/faults 基线不通过）"
  mr="$(bash tests/mutants/run_all.sh 2>&1 | tail -1)"
  [ "$mr" = "killed=8/8" ] || fail 12 "变异体未全杀：$mr"
  "$NODE" -e '
const fs=require("fs"),crypto=require("crypto"),path=require("path");
const d=JSON.parse(fs.readFileSync("cp12_audit.json","utf8"));
if(String(d.run_id||"")!==String(process.argv[1]).trim()){console.error("run_id 须等于 seed");process.exit(1);}
if(typeof d.verdict!=="string"||!d.verdict.trim()){console.error("verdict 为空");process.exit(1);}
const arr=Array.isArray(d.files)?d.files:[];
const skipDir=new Set(["clean",".fault-path",".git","tests"]);
const skipFile=new Set(["cp12_audit.json",".cp_state","advance.sh"]);
function walk(p){
  const out=[];
  for(const e of fs.readdirSync(p,{withFileTypes:true})){
    const full=path.join(p,e.name);
    const rel=path.relative(".",full);
    if(e.isDirectory()){ if(skipDir.has(e.name)) continue; out.push(...walk(full)); }
    else if(!skipFile.has(rel)) out.push(rel);
  }
  return out;
}
const real=walk(".");
const map=new Map();
for(const it of arr){ if(it&&it.path&&it.sha256) map.set(String(it.path),String(it.sha256)); }
for(const f of real){
  if(!map.has(f)){console.error("审计漏项 "+f);process.exit(1);}
  const h=crypto.createHash("sha256").update(fs.readFileSync(f)).digest("hex");
  if(map.get(f)!==h){console.error("审计 sha256 不符 "+f);process.exit(1);}
}
' "$SEED" || fail 12 "审计覆盖/哈希不通过"
}

check13() {
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    [ -f "notes/cp$i.md" ] || fail 13 "缺 notes/cp$i.md"
  done
  "$NODE" -e '
const fs=require("fs"),crypto=require("crypto");
for(let i=1;i<=12;i++){
  const p="notes/cp"+i+".md";
  const t=fs.readFileSync(p,"utf8");
  for(const h of ["## 结论","## 证据","## 判据"]) if(!t.includes(h)){console.error(p+" 缺 "+h);process.exit(1);}
  const re=/([^\s`|]+)\s+sha256=([0-9a-f]{64})/g;
  const hits=[...t.matchAll(re)];
  if(!hits.length){console.error(p+" 证据缺 路径 sha256=... 行");process.exit(1);}
  let ok=false;
  for(const h of hits){
    const raw=h[1]; const fp=raw.startsWith("./")?raw.slice(2):raw;
    try{
      if(crypto.createHash("sha256").update(fs.readFileSync(fp)).digest("hex")===h[2]){ok=true;break;}
    }catch(e){}
  }
  if(!ok){console.error(p+" 无可核验的证据行");process.exit(1);}
}
' || fail 13 "流程笔记不达标"
}

check14() {
  [ -f cp14_changes.json ] || fail 14 "缺 cp14_changes.json"
  "$NODE" -e '
const fs=require("fs"),crypto=require("crypto"),path=require("path"),{execSync}=require("child_process");
const d=JSON.parse(fs.readFileSync("cp14_changes.json","utf8"));
const arr=[...(d.changed||[]),...(d.added||[])];
if(!arr.length){console.error("没有任何变更记录");process.exit(1);}
let lines=0;
const allowRoot=/^cp[0-9]+_.*\.json$/;
const allowDir=/^(stage1|dist|clean|tasks|notes)\//;
for(const it of arr){
  let p=String(it.path||""); if(p.startsWith("./")) p=p.slice(2);
  if(!fs.existsSync(p)){console.error("记录的文件不存在 "+p);process.exit(1);}
  const h=crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
  if(h!==String(it.sha256)){console.error("sha256 不符 "+p);process.exit(1);}
  if(!allowDir.test(p)&&!allowRoot.test(p)){console.error("越界新增/改动 "+p);process.exit(1);}
  if(!(d.changed||[]).some(c=>String(c.path||"").replace(/^\.\//,"")===p)) continue;
  const rel=p.startsWith("stage1/")?p.slice(7):p; const base=path.join("stage0",rel);
  if(fs.existsSync(base)&&fs.statSync(base).isFile()){
    const out=execSync("diff -u "+JSON.stringify(base)+" "+JSON.stringify(p)+" || true",{encoding:"utf8"});
    lines+=out.split("\n").filter(l=>/^[+-]/.test(l)&&!/^(\+\+\+|---)/.test(l)).length;
  }
}
if(Number(d.changed_lines_total)!==lines){console.error("changed_lines_total 记录 "+d.changed_lines_total+" 实测 "+lines);process.exit(1);}
' || fail 14 "变更审计不达标"
}

check15() {
  [ -f cp9_resume.json ] || fail 15 "缺 cp9_resume.json"
  [ -f notes/cp9.md ] || fail 15 "缺 notes/cp9.md"
  grep -q '## Resumption Proof' notes/cp9.md || fail 15 "缺 ## Resumption Proof 段"
  for k in 可信检查点 中断 幂等; do
    grep -q "$k" notes/cp9.md || fail 15 "Resumption Proof 缺「$k」项"
  done
  "$NODE" -e '
const fs=require("fs"),crypto=require("crypto");
const d=JSON.parse(fs.readFileSync("cp9_resume.json","utf8"));
if(!/^[0-9a-f]{64}$/.test(String(d.rebuilt||""))){console.error("rebuilt 非法");process.exit(1);}
' || fail 15 "恢复证明与实测不符"
}

case "${1:-next}" in
  status) echo "done=$DONE" ;;
  next)
    next=$((DONE + 1))
    [ "$next" -gt 15 ] && { echo "全部完成"; exit 0; }
    echo "== 校验 cp$next"
    "check$next"
    echo "$next" > "$STATE"
    echo "cp$next 通过"
    ;;
  *) echo "用法: ./advance.sh [next|status]" >&2; exit 2 ;;
esac
