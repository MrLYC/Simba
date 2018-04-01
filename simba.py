#!/bin/env python3
# coding: utf-8

import argparse
import ast
import os
import re
from collections import namedtuple

import jedi

SPACE_PREFIX = re.compile(r"^\s*")


def safe_node_visitor(func):
    def wrapper(self, node):
        try:
            return func(self, node)
        except Exception:
            return node
    return wrapper


class Namespace(dict):
    __slots__ = ["name", "type", "inited"]

    def __init__(self, name, type=None, **kwargs):
        super(Namespace, self).__init__()
        self.name = name
        self.type = type or "unknown"
        self.inited = False
        if kwargs:
            self.init(**kwargs)

    def init(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.inited = True

    def __repr__(self):
        return "%s(%s)%r" % (
            self.__class__.__name__,
            ", ".join("%s=%r" % (k, getattr(self, k)) for k in self.__slots__),
            dict(self),
        )

    def __missing__(self, name):
        return Namespace(name)


class Anlyzer(ast.NodeTransformer):
    def __init__(self):
        super(Anlyzer, self).__init__()
        self.file = None
        self.code = None
        self.namespaces = {}
        self.solved_names = Namespace("", "root")

    def get_solved(self, path):
        info = self.solved_names
        for p in path:
            info = info[p]
        if info.inited:
            return info
        return None

    def solve_name(self, path, name, **kwargs):
        parent = self.solved_names
        for i in path.split("."):
            if not i:
                continue
            parent = parent[i]
        info = parent[name]
        if not info.inited:
            info.init(**kwargs)
            parent[name] = info
        return info

    def get_completions(self, script):
        return {
            c.name: c
            for c in script.completions()
        }

    def get_completions_by_code(self, code):
        interpreter = jedi.Interpreter(code, [self.namespaces])
        return self.get_completions(interpreter)

    def get_code(self, line, col, newline=True):
        lines = self.code[:line]
        last_line = lines[-1]
        if col:
            lines[-1] = last_line[:col + 1]
        elif newline:
            match = SPACE_PREFIX.search(last_line)
            lines.append(match.group())
        return os.linesep.join(lines)

    def get_code_by_node(self, node, newline=True):
        return self.get_code(node.lineno, node.col_offset)

    def get_completions_after_node(self, node, code):
        return self.get_completions_by_code(
            self.get_code_by_node(node) + code,
        )

    @safe_node_visitor
    def visit_ImportFrom(self, node):
        completions = self.get_completions_after_node(
            node, "from %s import " % (node.module),
        )
        for name in node.names:
            completion = completions.get(name.name)
            if completion is None:
                self.solve_name(node.module, name.name)
            else:
                self.solve_name(
                    node.module, name.name, type=completion.type,
                )
        return node

    @safe_node_visitor
    def visit_Import(self, node):
        for name in node.names:
            asname = name.asname or "_M"
            completions = self.get_completions_after_node(
                node, "import %s as %s\n%s." % (name.name, asname, asname),
            )
            parts = name.name.rsplit(".", 1)
            module = ".".join(parts[:-1])
            name = parts[-1]
            if completions:
                self.solve_name(module, name, type="module")
            else:
                self.solve_name(module, name)
        return node

    @safe_node_visitor
    def visit_Attribute(self, node):
        attrs = []
        attr = node
        while isinstance(attr, ast.Attribute):
            attrs.insert(0, attr.attr)
            attr = attr.value
        if isinstance(attr, ast.Name):
            attrs.insert(0, attr.id)
        parent = None
        for i in range(1, len(attrs)):
            path = attrs[:i]
            attr = attrs[i]
            chains = ".".join(path)
            completions = self.get_completions_after_node(node, chains)
            if parent is None:
                parent = completions.get(attr)
                if not parent:
                    self.solve_name("", attr)
                    break
            for name, completion in completions.items():
                if name == attr:
                    self.solve_name(
                        parent.module_name, name,
                        type=completion.type,
                    )
                    parent = completion
                    break
            else:
                self.solve_name(parent.module_name, name)

    def analysis(self, file):
        with open(file, "rt") as fp:
            code = fp.read()
        node = ast.parse(code)
        self.code = [""] + code.splitlines()
        self.visit(node)

    def get_unsolved(self):
        unsolved = set()
        def visit(root, prefix):
            for k, v in root.items():
                path = prefix + [k]
                if v.type == "unknown":
                    unsolved.add(".".join(path))
                if v:
                    visit(v, path)
        visit(self.solved_names, [])
        return unsolved


def main():
    parser = argparse.ArgumentParser("Python simple code analyzer")
    parser.add_argument("-m", "--module", help="module to anlyzer")
    parser.add_argument("file", nargs="+")

if __name__ == '__main__':
    main()
