#!/usr/bin/env python3
"""本地学习工作流：标准库、原子状态、答案隔离与可重试笔记投影。"""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from runtime_config import resolve_data_root

PLUGIN = Path(__file__).resolve().parents[1]
BEGIN = '<!-- ai-learning:managed:begin -->'
END = '<!-- ai-learning:managed:end -->'


class WorkflowError(Exception):
    def __init__(self, message, code='invalid_input', details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.learning-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_write(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def load_json(value):
    try:
        if str(value).lstrip().startswith(('{', '[')):
            return json.loads(value)
        return json.loads(Path(value).read_text(encoding='utf-8'))
    except (ValueError, OSError) as e:
        raise WorkflowError('无法读取 JSON：' + str(e))


def require(value, message):
    if not value:
        raise WorkflowError(message)


def slug(value):
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value), 'ID 需为英文、数字、短横线或下划线，最长80字符')
    return value


def within(base, relative):
    rel = Path(relative)
    require(not rel.is_absolute() and '..' not in rel.parts, '路径必须是主题内的相对路径')
    target = (base / rel).resolve()
    require(target != base and base in target.parents, '路径越出主题目录')
    return target


@contextlib.contextmanager
def locked(root):
    (root / 'state').mkdir(parents=True, exist_ok=True)
    with (root / 'state' / '.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


class Store:
    def __init__(self, root, topic):
        self.root = Path(root).resolve()
        self.topic = slug(topic)
        self.path = self.root / 'state' / (topic + '.json')
        self.workspace = self.root / '学习笔记库' / '主题' / topic
        self.state = json.loads(self.path.read_text()) if self.path.exists() else None

    def needed(self):
        require(self.state is not None, '主题未初始化，请先 topic-init')
        return self.state

    def save(self, update_sync=True):
        if update_sync:
            self.state['sync'] = dict(self.state['sync'], status='pending')
        self.state['updated_at'] = now()
        json_write(self.path, self.state)

    def event(self, kind, body):
        event = dict(id=str(uuid.uuid4()), at=now(), kind=kind, **body)
        self.state['events'].append(event)
        return event

    def public_quiz(self, quiz):
        if not quiz:
            return None
        spec = quiz['spec']
        out = {k: spec[k] for k in ['id', 'kind', 'phase', 'concept_id', 'question', 'source_refs'] if k in spec}
        out['options'] = quiz['display_options']
        out['status'] = 'pending'
        if spec['kind'] == 'open':
            out['rubric'] = spec['rubric']
        return out

    def status(self):
        s = self.needed()
        pending = self.public_quiz(s['pending'])
        awaiting = [dict(self.public_quiz(s['quizzes'][a['quiz_id']]), status='awaiting_evaluation',
                         attempt_id=a['id'], answer=a['answer'])
                    for a in s['attempts'] if a['outcome'] == 'awaiting_evaluation']
        mode = 'continue' if s['diagnosis']['finished'] else 'new_topic'
        action = ('await_user_answer' if pending else 'assess_open_answer' if any(a['outcome'] == 'awaiting_evaluation' for a in s['attempts']) else 'diagnose' if mode == 'new_topic' else 'plan_route' if not s['route']['nodes'] else 'continue_teaching')
        return dict(topic=self.topic, title=s['title'], workspace=str(self.workspace), mode=mode,
                    phase=s['phase'], next_action=action, pending_quiz=pending,
                    diagnosis=s['diagnosis'], route=s['route'], current_node=s['current_node'],
                    learning_records=s['records'], awaiting_evaluations=awaiting,
                    route_visual=s.get('route_visual'), sync=s['sync'])

    def initialize(self, title, mission, success):
        if self.state:
            require(self.state['title'] == title and self.state['mission'] == mission, '相同主题 ID 已有不同目标；请明确 mission-update 或创建新主题')
            return self.status()
        require(title.strip() and mission.strip() and success.strip(), '标题、实际目标和成功标准不能为空')
        require(not self.workspace.exists() or not any(self.workspace.iterdir()), '目标目录已有人工内容；请选新 ID，避免覆盖')
        for name in ['learning-records', 'lessons', 'reference', 'assets', 'sessions']:
            (self.workspace / name).mkdir(parents=True, exist_ok=True)
        self.state = dict(version=1, topic_id=self.topic, session_id=str(uuid.uuid4()), title=title,
                          mission=mission, success=success, phase='diagnosing', current_node=None,
                          diagnosis=dict(budget=6, answered=0, finished=False, skipped=False, frontier={}),
                          route=dict(nodes=[], edges=[]), pending=None, quizzes={}, attempts=[],
                          records=[], events=[], managed={}, sync=dict(status='pending', conflicts=[]))
        mission_text = f'# Mission: {title}\n\n## Why\n{mission}\n\n## Success looks like\n- {success}\n\n## Constraints\n中文教学；每次一个问题；诊断默认最多六题。\n\n## Out of scope\n按用户当前目标确定。\n'
        for rel, text in {'MISSION.md': mission_text, 'RESOURCES.md': f'# {title} Resources\n\n## Knowledge\n\n## Wisdom (Communities)\n\n## Gaps\n先核验当前课程需要的资料，再据此教学。\n', 'NOTES.md': '# 学习偏好\n\n在 Codex 学习和答题，在 Obsidian 保存记录。\nHTML 小测用于练习，不作为正式掌握证据。\n'}.items():
            atomic(self.workspace / rel, text)
            self.state['managed'][rel] = digest(text)
        self.event('topic_started', dict(title=title, mission=mission))
        self.save()
        self.sync()
        return self.status()

    def quiz_create(self, spec):
        s = self.needed()
        require(isinstance(spec, dict), '题目应为 JSON 对象')
        qid = slug(spec.get('id', ''))
        if s['pending']:
            require(s['pending']['spec'] == spec, '已有待答题；必须先等待、提交或明确取消')
            return dict(quiz=self.public_quiz(s['pending']), pending_quiz=self.public_quiz(s['pending']), resumed=True)
        require(not any(a['outcome'] == 'awaiting_evaluation' for a in s['attempts']), '先评阅已提交开放题，再出下一题')
        require(qid not in s['quizzes'], '题目 ID 已使用，请用新 ID')
        kind = spec.get('kind')
        require(kind in ['choice', 'multi', 'open'], 'kind 需为 choice/multi/open')
        require(spec.get('phase') in ['diagnostic', 'teaching', 'review'], 'phase 需为 diagnostic/teaching/review')
        require(isinstance(spec.get('question'), str) and spec['question'].strip(), '题面不能为空')
        require(isinstance(spec.get('concept_id'), str) and spec['concept_id'], '需明确 concept_id')
        if spec['phase'] == 'diagnostic':
            require(not s['diagnosis']['finished'], '首次诊断已完成；已有主题的局部检查使用 review，不重开诊断')
            require(s['diagnosis']['answered'] < s['diagnosis']['budget'], '诊断已达预算，请结束诊断，不能无限加难')
        elif not s['diagnosis']['finished'] or not s['route']['nodes']:
            raise WorkflowError('首次教学前需结束诊断并保存路线')
        options = spec.get('options', [])
        if kind != 'open':
            require(isinstance(options, list) and len(options) >= 2, '选择题至少两个选项')
            ids = [o.get('id') for o in options]
            require(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids), '选项 ID 必须唯一非空')
            require(all(isinstance(o.get('text'), str) and o['text'].strip() for o in options), '选项正文不能为空')
            correct = spec.get('correct')
            require(isinstance(correct, list) and correct and len(set(correct)) == len(correct) and set(correct) <= set(ids), '正确答案必须引用实际选项 ID')
            require(kind != 'choice' or len(correct) == 1, '单选题只能一个正确答案')
            require(isinstance(spec.get('explanation'), str) and spec['explanation'].strip(), '需提供答后解析')
        else:
            require(isinstance(spec.get('rubric'), str) and spec['rubric'].strip(), '开放题需明确 rubric')
            require(not options, '开放题不提供选项')
        shown = list(options)
        if spec.get('shuffle', True):
            random.SystemRandom().shuffle(shown)
        quiz = dict(spec=spec, display_options=shown, created_at=now())
        s['quizzes'][qid] = quiz
        s['pending'] = quiz
        self.event('quiz_issued', dict(quiz=self.public_quiz(quiz)))
        self.save()
        self.sync()
        return dict(quiz=self.public_quiz(quiz), pending_quiz=self.public_quiz(quiz), resumed=False)

    def submit(self, qid, aid, answer):
        s = self.needed()
        slug(aid)
        require(isinstance(answer, dict), '答案应为 JSON 对象')
        previous = next((a for a in s['attempts'] if a['id'] == aid), None)
        if previous:
            require(previous['quiz_id'] == qid and previous['answer'] == answer, '同一 attempt ID 不能提交不同内容')
            return dict(result=previous, idempotent=True)
        resolved = next((a for a in s['attempts'] if a['quiz_id'] == qid), None)
        if resolved:
            require(resolved['answer'] == answer, '同一已提交题不能改答；复测请创建新题')
            return dict(result=resolved, idempotent=True)
        require(s['pending'] and s['pending']['spec']['id'] == qid, '题目不是当前待答题')
        spec = s['pending']['spec']
        supplied = [k for k in ['selection', 'text', 'dont_know', 'cancelled'] if k in answer]
        require(len(supplied) == 1, '只能提交一种答题状态')
        if 'dont_know' in answer or 'cancelled' in answer:
            require(answer[supplied[0]] is True, '不会/取消标志需为 true')
            outcome = 'dont_know' if 'dont_know' in answer else 'cancelled'
        elif spec['kind'] == 'open':
            require(isinstance(answer.get('text'), str) and answer['text'].strip(), '开放题需非空 text')
            outcome = 'awaiting_evaluation'
        else:
            selected = answer.get('selection')
            require(isinstance(selected, list) and selected and all(isinstance(v, str) for v in selected) and len(set(selected)) == len(selected), 'selection 应为不重复的选项 ID 列表')
            require(set(selected) <= {o['id'] for o in spec['options']}, '选择了不存在的选项 ID')
            require(spec['kind'] != 'choice' or len(selected) == 1, '单选题只能选择一项')
            outcome = 'correct' if set(selected) == set(spec['correct']) else 'wrong'
        result = dict(id=aid, quiz_id=qid, concept_id=spec['concept_id'], phase=spec['phase'],
                      answer=answer, outcome=outcome, at=now())
        if outcome not in ['awaiting_evaluation', 'cancelled']:
            result['explanation'] = spec.get('explanation', '')
            if 'correct' in spec:
                result['correct'] = spec['correct']
        s['attempts'].append(result)
        s['pending'] = None
        self.event('quiz_answered', dict(result=result))
        if spec['phase'] == 'diagnostic' and outcome != 'cancelled':
            s['diagnosis']['answered'] += 1
            self.frontier(result)
        self.save()
        self.sync()
        return dict(result=result, idempotent=False)

    def frontier(self, result):
        f = self.state['diagnosis']['frontier'].setdefault(result['concept_id'], dict(correct=[], gaps=[], unresolved=[]))
        target = 'correct' if result['outcome'] == 'correct' else 'gaps' if result['outcome'] in ['wrong', 'dont_know'] else 'unresolved'
        if result['quiz_id'] not in f[target]:
            f[target].append(result['quiz_id'])
        if target != 'unresolved' and result['quiz_id'] in f['unresolved']:
            f['unresolved'].remove(result['quiz_id'])
        f['summary'] = '已确认下界，上界未定位' if f['correct'] and not f['gaps'] else '已定位缺口，结合邻近题判断边界' if f['gaps'] else '尚未确认'

    def assess(self, qid, assessment):
        s = self.needed()
        a = next((a for a in s['attempts'] if a['quiz_id'] == qid), None)
        require(a and s['quizzes'][qid]['spec']['kind'] == 'open', '只能评阅已提交开放题')
        if 'assessment' in a:
            require(a['assessment'] == assessment, '已评阅题不能用不同结论覆写')
            return dict(result=a, idempotent=True)
        require(a['outcome'] == 'awaiting_evaluation', '该作答不需要评阅')
        require(assessment.get('outcome') in ['correct', 'wrong'], '评阅 outcome 需为 correct/wrong')
        for key in ['rationale', 'model', 'rubric']:
            require(isinstance(assessment.get(key), str) and assessment[key].strip(), '评阅需实际 ' + key)
        require(assessment['rubric'] == s['quizzes'][qid]['spec']['rubric'], '评阅标准必须与题目 rubric 一致')
        a.update(outcome=assessment['outcome'], assessment=assessment, explanation=assessment['rationale'])
        self.event('quiz_assessed', dict(quiz_id=qid, assessment=assessment))
        if a['phase'] == 'diagnostic':
            self.frontier(a)
        self.save()
        self.sync()
        return dict(result=a, idempotent=False)

    def finish(self, skip=False):
        s = self.needed()
        require(not s['pending'], '仍有待答题，先等待或明确取消')
        require(not any(a['outcome'] == 'awaiting_evaluation' and a['phase'] == 'diagnostic' for a in s['attempts']), '先完成开放题评阅')
        if not s['diagnosis']['finished']:
            s['diagnosis'].update(finished=True, skipped=skip, finished_at=now())
            s['phase'] = 'planning'
            self.event('diagnosis_finished', dict(skipped=skip, answered=s['diagnosis']['answered']))
            self.save()
        self.sync()
        return self.status()

    def set_route(self, incoming, replace=False):
        s = self.needed()
        require(isinstance(incoming, dict) and isinstance(incoming.get('nodes'), list) and isinstance(incoming.get('edges'), list), '路线需 nodes/edges 数组')
        require(s['diagnosis']['finished'], '先结束或跳过诊断，再规划路线')
        nodes = {} if replace else {n['id']: n for n in s['route']['nodes']}
        record_ids = {r['id'] for r in s['records'] if r['kind'] in ['demonstrated', 'correction'] and r['status'] == 'active'}
        seen = set()
        for n in incoming['nodes']:
            nid = slug(n.get('id', ''))
            require(nid not in seen, '输入包含重复节点')
            seen.add(nid)
            require(n.get('label') and n.get('status') in ['confirmed', 'pending', 'unknown'], '节点需 label 与 confirmed/pending/unknown 状态')
            require(isinstance(n.get('source_refs', []), list) and isinstance(n.get('evidence_refs', []), list), '来源与证据需数组')
            if n['status'] == 'confirmed':
                require(n.get('evidence_refs') and set(n['evidence_refs']) <= record_ids, '已确认概念需有效的理解或纠错证据；自述先验和目标变化不能单独确认掌握')
            nodes[nid] = n
        edges = [] if replace else list(s['route']['edges'])
        for e in incoming['edges']:
            require(isinstance(e, list) and len(e) == 2 and all(isinstance(v, str) for v in e) and all(v in nodes for v in e), '每条边需两个已有节点 ID')
            if e not in edges:
                edges.append(e)
        adj = {v: [] for v in nodes}
        for a, b in edges:
            require(a in nodes and b in nodes, '现有边引用了被移除节点')
            adj[a].append(b)
        active, done = set(), set()
        def visit(v):
            require(v not in active, '路线存在循环依赖')
            if v in done:
                return
            active.add(v)
            for w in adj[v]:
                visit(w)
            active.remove(v)
            done.add(v)
        for v in adj:
            visit(v)
        s['route'] = dict(nodes=list(nodes.values()), edges=edges)
        self.event('route_updated', dict(changed_nodes=sorted(seen), replaced=replace))
        self.save()
        self.sync()
        return dict(route=s['route'])

    def route_visual(self, manifest):
        s = self.needed()
        require(s['route']['nodes'], '需先保存路线')
        data = load_json(manifest)
        require(data.get('status') == 'rendered' and data.get('visual_verified') is True, '路线图需成功渲染且已亲自看图检查')
        workspace = self.workspace.resolve()
        paths = {}
        for key in ['png', 'source', 'log']:
            path = Path(data[key]).resolve()
            require(workspace in path.parents and path.is_file(), '路线图产物必须保存在本主题目录内')
            paths[key] = str(path.relative_to(workspace))
        visual = dict(paths, route_hash=digest(json.dumps(s['route'], sort_keys=True, ensure_ascii=False)),
                      png_hash=digest(Path(data['png']).read_bytes()), verification_note=data.get('verification_note'))
        if s.get('route_visual') == visual:
            self.sync()
            return dict(route_visual=visual, sync=s['sync'], idempotent=True)
        s['route_visual'] = visual
        self.event('route_visual_linked', dict(png=paths['png']))
        self.save()
        self.sync()
        return dict(route_visual=s['route_visual'], sync=s['sync'], idempotent=False)

    def checkpoint(self, phase, node=None, note=None):
        s = self.needed()
        require(not s['pending'] or (phase == s['phase'] and node == s['current_node']), '待答题未完成，不能跨过题目推进教学')
        require(not any(a['outcome'] == 'awaiting_evaluation' for a in s['attempts']) or (phase == s['phase'] and node == s['current_node']), '先完成开放题评阅，再推进教学')
        if phase in ['teaching', 'reviewing', 'complete']:
            require(s['diagnosis']['finished'] and s['route']['nodes'], '首次教学前需结束诊断并保存路线')
        if node:
            require(node in {n['id'] for n in s['route']['nodes']}, '断点节点不在路线内')
        s.update(phase=phase, current_node=node or s['current_node'])
        self.event('checkpoint', dict(phase=phase, node=s['current_node'], note=note))
        self.save()
        self.sync()
        return self.status()

    def record(self, record):
        s = self.needed()
        for k in ['title', 'summary', 'evidence']:
            require(isinstance(record.get(k), str) and record[k].strip(), '学习记录需具体 ' + k)
        kind = record.get('kind')
        require(kind in ['demonstrated', 'prior_knowledge', 'correction', 'mission_change'], '学习记录 kind 不支持')
        refs = record.get('evidence_refs', [])
        require(isinstance(refs, list), 'evidence_refs 需数组')
        if kind in ['demonstrated', 'correction']:
            valid = {a['quiz_id'] for a in s['attempts'] if a['outcome'] == 'correct'}
            require(refs and set(refs) <= valid, '理解记录需已评阅正确的作答引用；仅阅读/答错不是掌握证据')
        if kind == 'mission_change':
            require(any(e['kind'] == 'mission_changed' for e in s['events']), '任务变化尚未确认记录')
        fingerprint = digest(json.dumps(record, ensure_ascii=False, sort_keys=True))
        old = next((r for r in s['records'] if r['fingerprint'] == fingerprint), None)
        if old:
            return dict(record=old, idempotent=True)
        rid = f"{len(s['records']) + 1:04d}"
        if record.get('supersedes'):
            previous = next((r for r in s['records'] if r['id'] == record['supersedes']), None)
            require(previous, '被取代记录不存在')
            previous['status'] = 'superseded by LR-' + rid
        saved = dict(record, id=rid, at=now(), fingerprint=fingerprint, status='active')
        s['records'].append(saved)
        self.event('learning_recorded', dict(record_id=rid))
        self.save()
        self.sync()
        return dict(record=saved, idempotent=False)

    def review(self):
        s = self.needed()
        latest = {}
        for a in s['attempts']:
            if a['outcome'] != 'cancelled':
                latest[a['concept_id']] = a
        return dict(items=[dict(concept_id=k, outcome=a['outcome'], quiz_id=a['quiz_id']) for k, a in latest.items() if a['outcome'] in ['wrong', 'dont_know']], records=s['records'])

    def safe_projection(self, relative, body):
        path = within(self.workspace.resolve(), relative)
        current = path.read_text(encoding='utf-8') if path.exists() else None
        managed_text = BEGIN + '\n' + body.rstrip() + '\n' + END + '\n'
        if current is not None and BEGIN in current and END in current:
            left, rest = current.split(BEGIN, 1)
            _, right = rest.split(END, 1)
            desired = left + managed_text.rstrip('\n') + right
        else:
            desired = managed_text
        if current == desired:
            self.state['managed'][relative] = digest(current)
            return None
        previous = self.state['managed'].get(relative)
        if current is not None and (previous is None or digest(current) != previous):
            folder = self.root / 'state' / 'conflicts' / self.topic
            candidate = folder / (digest(relative)[:10] + '-' + path.name + '.merge')
            atomic(candidate, desired)
            return dict(path=str(path), relative_path=relative, expected_hash=digest(current), merge_path=str(candidate))
        atomic(path, desired)
        self.state['managed'][relative] = digest(desired)
        return None

    def sync(self):
        s = self.needed()
        files = {}
        title = s['title']
        route = s['route']
        lines = ['graph TD']
        labels = {'confirmed': '已确认', 'pending': '待学习', 'unknown': '未确认'}
        for n in route['nodes']:
            label = html.escape(n['label'], quote=True).replace('\n', ' ')
            lines.append(f'  {n["id"]}["{label} · {labels[n["status"]]}"]')
        for a, b in route['edges']:
            lines.append(f'  {a} --> {b}')
        visual = s.get('route_visual')
        visual_current = bool(visual and visual['route_hash'] == digest(json.dumps(route, sort_keys=True, ensure_ascii=False)))
        if visual_current:
            png = within(self.workspace.resolve(), visual['png'])
            visual_current = png.is_file() and digest(png.read_bytes()) == visual['png_hash']
        if visual_current:
            route_doc = '# 学习路线\n\n![' + title + ' 知识依赖图](' + visual['png'].replace(' ', '%20') + ')\n\n'
            route_doc += '[Mermaid/SVG 源码](' + visual['source'].replace(' ', '%20') + ')\n\n'
        else:
            route_doc = '# 学习路线\n\n图示待渲染或更新；以下为当前路线源码，尚未确认图片。\n\n```mermaid\n' + '\n'.join(lines) + '\n```\n\n'
        for n in route['nodes']:
            route_doc += f'- **{n["label"]}**：{labels[n["status"]]}；来源：' + ', '.join(n.get('source_refs', [])) + '；证据：' + ', '.join(n.get('evidence_refs', [])) + '\n'
        if route['nodes']:
            files['学习路线.md'] = route_doc
        courses = sorted((self.workspace / 'lessons').glob('*.html'))
        records = ['- [[' + f'learning-records/{r["id"]}-learning.md' + '|' + r['title'] + ']]' for r in s['records']]
        index = f'# {title}\n\n目标：{s["mission"]}\n\n成功标准：{s["success"]}\n\n阶段：{s["phase"]}；当前概念：{s["current_node"] or "待规划"}\n\n'
        index += '[[MISSION]] · [[RESOURCES]] · [[NOTES]]' + (' · [[学习路线]]' if route['nodes'] else '') + '\n\n## 课程\n\n'
        index += '\n'.join('- [' + p.name + '](lessons/' + p.name.replace(' ', '%20') + ')' for p in courses) or '尚无课程；在本主题目录显式调用 teach。'
        index += '\n\n## 学习记录\n\n' + ('\n'.join(records) or '等待真实理解证据。')
        index += '\n\n## 本次课时\n\n[[sessions/' + s['session_id'] + '|学习流水]]\n'
        files['课程索引.md'] = index
        log = f'# {title} · 课时流水\n\n'
        for e in s['events']:
            log += f'## {e["at"]} · {e["kind"]}\n\n'
            if e['kind'] == 'quiz_issued':
                q = e['quiz']
                log += q['question'] + '\n\n'
                for o in q['options']:
                    log += '- ' + o['id'] + '：' + o['text'] + '\n'
                log += '\n可回答“不知道”或明确取消。\n'
            elif e['kind'] == 'quiz_answered':
                a = e['result']
                log += '状态：' + a['outcome'] + '\n\n作答：' + json.dumps(a['answer'], ensure_ascii=False) + '\n'
                if 'explanation' in a:
                    log += '\n解析：' + a['explanation'] + '\n'
                if 'correct' in a:
                    log += '\n正确选项 ID：' + ', '.join(a['correct']) + '\n'
            elif e['kind'] == 'quiz_assessed':
                log += json.dumps(e['assessment'], ensure_ascii=False, indent=2) + '\n'
            else:
                log += json.dumps({k: v for k, v in e.items() if k not in ['id', 'at', 'kind']}, ensure_ascii=False) + '\n'
            log += '\n'
        files['sessions/' + s['session_id'] + '.md'] = log
        for r in s['records']:
            body = f'---\nstatus: {r["status"]}\nkind: {r["kind"]}\n---\n\n# {r["title"]}\n\n{r["summary"]}\n\n## Evidence\n{r["evidence"]}\n\n引用：' + ', '.join(r.get('evidence_refs', [])) + '\n'
            if r.get('implications'):
                body += '\n## Implications\n' + r['implications'] + '\n'
            files['learning-records/' + r['id'] + '-learning.md'] = body
        conflicts = []
        for rel, body in files.items():
            conflict = self.safe_projection(rel, body)
            if conflict:
                conflicts.append(conflict)
        s['sync'] = dict(status='conflict' if conflicts else 'synced', conflicts=conflicts, at=now())
        self.save(update_sync=False)
        return dict(sync=s['sync'], workspace=str(self.workspace))

    def patch(self, relative, content, expected_hash=None):
        s = self.needed()
        path = within(self.workspace.resolve(), relative)
        current = path.read_text(encoding='utf-8') if path.exists() else None
        if current is not None:
            require(expected_hash and digest(current) == expected_hash, '文件已变化或未提供 expected-hash；不覆盖')
        atomic(path, content)
        s['managed'][relative] = digest(content)
        self.event('note_patched', dict(path=relative))
        self.save()
        return dict(path=str(path), hash=digest(content))


def vault_status(root):
    cfg = root / 'deployment.json'
    deployment = json.loads(cfg.read_text()) if cfg.exists() else {}
    obsidian = shutil.which('obsidian')
    desired = (root / '学习笔记库').resolve()
    metadata = Path.home() / 'Library/Application Support/obsidian/obsidian.json'
    vaults = json.loads(metadata.read_text()).get('vaults', {}) if metadata.exists() else {}
    found = next((key for key, value in vaults.items() if Path(value['path']).resolve() == desired), None)
    return dict(cli=obsidian, vault_path=str(desired), registered_vault_id=found,
                configured_vault_id=deployment.get('vault_id'), ready=bool(obsidian and found and deployment.get('vault_id') == found))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path)
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('topic-init')
    for name in ['id', 'title', 'mission', 'success']:
        init.add_argument('--' + name, required=True)
    names = ['status', 'diagnosis-finish', 'checkpoint', 'quiz-create', 'quiz-submit', 'quiz-assess', 'route-set', 'route-visual', 'record-learning', 'sync', 'note-patch', 'review-list', 'open', 'mission-update']
    for name in names:
        q = sub.add_parser(name)
        q.add_argument('--topic', required=True)
        if name in ['quiz-create', 'quiz-assess', 'route-set', 'record-learning', 'note-patch']:
            q.add_argument('--file', required=True)
        if name in ['quiz-submit', 'quiz-assess']:
            q.add_argument('--quiz', required=True)
        if name == 'quiz-submit':
            q.add_argument('--attempt', required=True)
            q.add_argument('--answer', required=True)
        if name == 'route-set':
            q.add_argument('--replace', action='store_true')
        if name == 'route-visual':
            q.add_argument('--manifest', required=True)
        if name == 'diagnosis-finish':
            q.add_argument('--skip', action='store_true')
        if name == 'checkpoint':
            q.add_argument('--phase', required=True, choices=['diagnosing', 'planning', 'teaching', 'reviewing', 'complete'])
            q.add_argument('--node')
            q.add_argument('--note')
        if name in ['note-patch', 'open']:
            q.add_argument('--path', default='课程索引.md')
        if name == 'open':
            q.add_argument('--target', choices=['auto', 'obsidian', 'browser'], default='auto')
        if name == 'note-patch':
            q.add_argument('--expected-hash')
        if name == 'mission-update':
            q.add_argument('--mission', required=True)
            q.add_argument('--success', required=True)
            q.add_argument('--confirmed', action='store_true')
    sub.add_parser('vault-status')
    render = sub.add_parser('render')
    render.add_argument('--kind', choices=['mermaid', 'svg'], required=True)
    render.add_argument('--input', required=True)
    render.add_argument('--output-dir', required=True)
    render.add_argument('--stem')
    verify = sub.add_parser('diagram-verify')
    verify.add_argument('--manifest', required=True)
    verify.add_argument('--note', required=True)
    return p


def run(a):
    root = resolve_data_root(a.root)
    root = root.resolve()
    if a.command == 'render':
        from diagram_renderer import render_diagram
        return render_diagram(a.input, a.kind, a.output_dir, a.stem)
    if a.command == 'diagram-verify':
        data = load_json(a.manifest)
        require(data.get('status') == 'rendered' and Path(data['png']).exists(), '需有成功渲染的 PNG')
        require(a.note.strip(), '需具体视觉检查结论')
        data.update(visual_verified=True, verification_note=a.note, verified_at=now())
        json_write(Path(a.manifest), data)
        return data
    if a.command == 'vault-status':
        return vault_status(root)
    with locked(root):
        store = Store(root, a.id if a.command == 'topic-init' else a.topic)
        if a.command == 'topic-init':
            return store.initialize(a.title, a.mission, a.success)
        store.needed()
        if a.command == 'status':
            return store.status()
        if a.command == 'quiz-create':
            return store.quiz_create(load_json(a.file))
        if a.command == 'quiz-submit':
            return store.submit(a.quiz, a.attempt, load_json(a.answer))
        if a.command == 'quiz-assess':
            return store.assess(a.quiz, load_json(a.file))
        if a.command == 'diagnosis-finish':
            return store.finish(a.skip)
        if a.command == 'route-set':
            return store.set_route(load_json(a.file), a.replace)
        if a.command == 'route-visual':
            return store.route_visual(a.manifest)
        if a.command == 'checkpoint':
            return store.checkpoint(a.phase, a.node, a.note)
        if a.command == 'record-learning':
            return store.record(load_json(a.file))
        if a.command == 'sync':
            result = store.sync()
            if result['sync']['status'] == 'conflict':
                raise WorkflowError('检测到人工修改，原文件保留；请审阅待合并版本', 'conflict', result)
            return result
        if a.command == 'note-patch':
            return store.patch(a.path, Path(a.file).read_text(encoding='utf-8'), a.expected_hash)
        if a.command == 'review-list':
            return store.review()
        if a.command == 'mission-update':
            require(a.confirmed, '需用户已明确确认目标变化，才传 --confirmed')
            target = store.workspace / 'MISSION.md'
            require(digest(target.read_text()) == store.state['managed'].get('MISSION.md'), 'MISSION.md 有人工变更，请先审阅并用 note-patch 合并')
            require(a.mission.strip() and a.success.strip(), '实际目标和成功标准不能为空')
            text = target.read_text(encoding='utf-8')
            for heading, body in [('Why', a.mission), ('Success looks like', '- ' + a.success)]:
                pattern = r'(?m)^## ' + re.escape(heading) + r'\s*\n[\s\S]*?(?=^## |\Z)'
                require(re.search(pattern, text), 'MISSION.md 结构已变化；请用 note-patch 审阅合并')
                text = re.sub(pattern, lambda _: '## ' + heading + '\n' + body + '\n\n', text, count=1)
            store.state.update(mission=a.mission, success=a.success)
            atomic(target, text)
            store.state['managed']['MISSION.md'] = digest(text)
            store.event('mission_changed', dict(mission=a.mission, success=a.success))
            store.save()
            store.sync()
            return store.status()
        if a.command == 'open':
            path = within(store.workspace.resolve(), a.path)
            require(path.exists(), '文件不存在')
            target = ('browser' if path.suffix.lower() in ['.html', '.htm'] else 'obsidian') if a.target == 'auto' else a.target
            if target == 'browser':
                require(path.suffix.lower() in ['.html', '.htm'], '浏览器打开仅支持主题中的本地 HTML')
                opener = shutil.which('open') if sys.platform == 'darwin' else shutil.which('xdg-open')
                require(opener, '未找到系统文件打开命令；请在 Codex 浏览器打开返回路径')
                process = subprocess.run([opener, str(path)], capture_output=True, text=True, timeout=25)
                require(process.returncode == 0, '浏览器打开失败：' + process.stderr)
                return dict(path=str(path), target='browser', output=process.stdout.strip())
            status = vault_status(root)
            require(status['ready'], '专用 Vault 未登记或 deployment.json 不匹配，请先完成 Obsidian 注册')
            relative = str(path.relative_to(root / '学习笔记库'))
            process = subprocess.run([status['cli'], 'vault=' + status['registered_vault_id'], 'open', 'path=' + relative], capture_output=True, text=True, timeout=25)
            require(process.returncode == 0, 'Obsidian 打开失败：' + process.stderr)
            return dict(path=str(path), target='obsidian', vault_id=status['registered_vault_id'], output=process.stdout.strip())
    raise WorkflowError('未知命令')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    args = parser().parse_args()
    try:
        result = run(args)
        print(json.dumps(dict(ok=True, **result), ensure_ascii=False))
        return 0
    except Exception as e:
        details = getattr(e, 'details', {})
        if hasattr(e, 'result'):
            details = e.result
        code = getattr(e, 'code', 'operation_failed')
        result = dict(details)
        result.update(ok=False, error=str(e), error_code=code)
        print(json.dumps(result, ensure_ascii=False))
        return 2 if code == 'conflict' else 1


if __name__ == '__main__':
    sys.exit(main())
