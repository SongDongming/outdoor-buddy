"""
Aho-Corasick 多模式匹配自动机（纯 Python 实现，零依赖）

在文本中一次性查找大量关键词，时间复杂度 O(文本长度 + 命中数)，与关键词数量无关。
适用于内容审核的关键词秒拦（词表可到数万条，朴素逐词扫描会退化到 O(词数×文本长度)）。

用法:
    matcher = AhoCorasick(["色情", "暴恐", ...])
    matcher.contains(text)        # bool 是否有命中
    matcher.search(text)          # list 命中的关键词（去重）
"""

from collections import deque

# 节点用普通 dict 表示（char -> child_node），用 id(node) 作节点唯一标识。
# 节点会被 trie 结构持续引用，不会被 GC，因此 id 稳定。


class AhoCorasick:
    """Aho-Corasick 自动机"""

    def __init__(self, keywords=None):
        self._root = {}
        self._fail: dict[int, dict] = {}
        self._out: dict[int, list] = {}
        self._keywords: set[str] = set()
        if keywords:
            self.build(keywords)

    def build(self, keywords: list[str]) -> "AhoCorasick":
        """构建自动机。keywords 为关键词列表（可重复，自动去重）"""
        self._root = {}
        self._fail = {}
        self._out = {}
        self._keywords = set(k for k in keywords if k)

        # 1) 建 Trie
        for kw in self._keywords:
            node = self._root
            for ch in kw:
                node = node.setdefault(ch, {})
            self._out.setdefault(id(node), []).append(kw)

        # 2) BFS 构建失败指针（fail）
        root = self._root
        queue: deque[dict] = deque()
        for child in root.values():
            self._fail[id(child)] = root
            queue.append(child)

        while queue:
            node = queue.popleft()
            nid = id(node)
            for ch, child in node.items():
                queue.append(child)
                f = self._fail.get(nid, root)
                while f is not root and ch not in f:
                    f = self._fail.get(id(f), root)
                self._fail[id(child)] = f.get(ch, root)
                # 合并失败节点上以该处结尾的词到当前节点输出
                fo = self._out.get(id(self._fail[id(child)]))
                if fo:
                    self._out.setdefault(id(child), []).extend(fo)

        return self

    def _goto(self, node: dict, ch: str) -> dict:
        """沿文本走自动机：若当前节点无该字符，则沿 fail 回溯到可匹配的节点"""
        while node is not self._root and ch not in node:
            node = self._fail.get(id(node), self._root)
        return node.get(ch, self._root)

    def contains(self, text: str) -> bool:
        """文本中是否有任一关键词命中（找到即返回 True）"""
        if not text or not self._keywords:
            return False
        node = self._root
        for ch in text:
            node = self._goto(node, ch)
            if self._out.get(id(node)):
                return True
        return False

    def search(self, text: str) -> list[str]:
        """返回文本中命中的关键词（去重、保首次出现顺序）"""
        if not text or not self._keywords:
            return []
        result: list[str] = []
        node = self._root
        for ch in text:
            node = self._goto(node, ch)
            outs = self._out.get(id(node))
            if outs:
                result.extend(outs)
        return list(dict.fromkeys(result))

    def __len__(self) -> int:
        return len(self._keywords)
