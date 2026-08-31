"""
语料库管理 — 为数据生成提供原始文本素材
"""
import os
import random
import hashlib
import json
from config import ROOT, DATA_DIR, SEED

random.seed(SEED)


def _scan_python_sources():
    """扫描系统Python标准库源码"""
    sources = []
    python_lib = "/usr/lib/python3.13"
    if not os.path.exists(python_lib):
        python_lib = "/usr/lib/python3"
    if os.path.exists(python_lib):
        for root, _, files in os.walk(python_lib):
            for f in files:
                if f.endswith('.py'):
                    try:
                        with open(os.path.join(root, f), 'rb') as fh:
                            data = fh.read()
                            if 512 < len(data) < 50000:
                                sources.append(data)
                    except:
                        pass
    return sources


def _generate_chinese_samples():
    """生成中文文本样本"""
    templates = [
        "第{i}号文件记录：系统运行状态正常，当前时间戳为{ts}。数据处理模块已完成初始化，"
        "等待上级指令下发。网络连接状态良好，防火墙规则已加载。日志记录器启动完成，"
        "开始监控所有接口流量。安全策略已生效，入侵检测引擎进入在线模式。"
        "内存使用率：{mem}%，CPU负载：{cpu}%，磁盘剩余空间：{disk}GB。"
        "系统管理员{name}已登录，执行了{cmd}命令，操作结果为：{result}。",
    ]
    names = ["管理员", "张三", "李四", "王五", "赵六", "运维人员", "审计员"]
    cmds = ["ifconfig", "netstat -an", "ps aux", "top -n 1", "df -h", "iptables -L",
            "ls -la /var/log", "grep ERROR /var/log/syslog", "tcpdump -i eth0 -c 10"]

    samples = []
    for i in range(2000):
        t = random.choice(templates)
        s = t.format(i=i, ts=f"2026-{random.randint(1,12):02d}-{random.randint(1,28):02d}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}",
                     mem=random.randint(20, 95), cpu=random.randint(5, 98),
                     disk=random.randint(50, 500), name=random.choice(names),
                     cmd=random.choice(cmds), result=random.choice(["成功", "失败", "超时", "拒绝"]))
        samples.append(s.encode('utf-8'))
    return samples


def _generate_json_samples():
    """生成JSON结构数据"""
    samples = []
    for i in range(1000):
        obj = {
            "id": i,
            "timestamp": f"2026-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "event": random.choice(["login", "logout", "alert", "info", "error"]),
            "source_ip": f"192.168.{random.randint(1,255)}.{random.randint(1,255)}",
            "dest_ip": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,255)}",
            "port": random.choice([22, 80, 443, 3306, 6379, 8080]),
            "user": random.choice(["admin", "user", "root", "service", "nobody"]),
            "message": f"Event {i}: operation completed",
            "metadata": {
                "severity": random.randint(1, 10),
                "category": random.choice(["auth", "network", "system", "app"]),
                "duration_ms": random.randint(1, 5000)
            }
        }
        samples.append(json.dumps(obj, ensure_ascii=False).encode('utf-8'))
    return samples


def _generate_xml_samples():
    """生成XML/HTML数据"""
    samples = []
    for i in range(1000):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<record id="{i}">\n'
            f'  <timestamp>2026-{random.randint(1,12):02d}-{random.randint(1,28):02d}</timestamp>\n'
            f'  <type>{random.choice(["request", "response", "event", "error"])}</type>\n'
            f'  <source>{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}</source>\n'
            f'  <payload size="{random.randint(64,4096)}">\n'
            f'    <content><![CDATA[Sample content {i} with some data.]]></content>\n'
            f'  </payload>\n'
            f'  <checksum>{hashlib.md5(str(i).encode()).hexdigest()}</checksum>\n'
            f'</record>'
        )
        samples.append(xml.encode('utf-8'))
    return samples


def build_corpus_pool():
    """构建并缓存语料池"""
    cache_file = os.path.join(DATA_DIR, "corpus_pool.txt")
    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as f:
            return f.read().split(b'\n---CORPUS_SEP---\n')

    pool = []

    # 1. Python源码 (最多)
    py_srcs = _scan_python_sources()
    pool.extend(py_srcs)

    # 2. 英语文本 (从系统字典生成)
    try:
        with open('/usr/share/dict/words', 'r') as f:
            words = [w.strip() for w in f.readlines() if 3 < len(w.strip()) < 15]
        random.shuffle(words)
        for i in range(2000):
            n_words = random.randint(50, 200)
            text = ' '.join(random.choices(words, k=n_words))
            pool.append(text.encode('utf-8'))
    except:
        pass

    # 3. 中文文本
    try:
        ch_samples = _generate_chinese_samples()
        pool.extend(ch_samples)
    except:
        pass

    # 4. JSON
    json_samples = _generate_json_samples()
    pool.extend(json_samples)

    # 5. XML
    xml_samples = _generate_xml_samples()
    pool.extend(xml_samples)

    # 6. C/C++源码 (从系统头文件)
    try:
        for d in ['/usr/include', '/usr/local/include']:
            if os.path.exists(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.endswith(('.h', '.c', '.cpp', '.hpp')):
                            try:
                                with open(os.path.join(root, f), 'rb') as fh:
                                    data = fh.read()
                                    if 256 < len(data) < 20000:
                                        pool.append(data)
                            except:
                                pass
    except:
        pass

    # 去重 + 过滤太短/太长的
    seen = set()
    unique = []
    for p in pool:
        h = hashlib.md5(p).hexdigest()
        if h not in seen and len(p) > 128:
            seen.add(h)
            unique.append(p)

    random.shuffle(unique)
    # 限制语料池大小
    pool = unique[:25000]

    # 缓存
    with open(cache_file, 'wb') as f:
        f.write(b'\n---CORPUS_SEP---\n'.join(pool))

    return pool


def get_corpus():
    """获取语料池(单例)"""
    return build_corpus_pool()


if __name__ == "__main__":
    pool = build_corpus_pool()
    print(f"语料池: {len(pool)} 条")
    if pool:
        print(f"样本长度: [{min(len(p) for p in pool)}, {max(len(p) for p in pool)}]")
