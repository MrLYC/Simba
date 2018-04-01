#!/bin/env python3
# coding: utf-8

import argparse
import ast
import os
import re
from collections import namedtuple

import jedi

SPACE_PREFIX = re.compile(r"^\s*")


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

    def solve_name(self, module, name, **kwargs):
        parent = self.solved_names
        for i in module.split("."):
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

    def get_completions_by_interpreter(self, code):
        interpreter = jedi.Interpreter(code, [self.namespaces])
        return self.get_completions(interpreter)

    def get_code(self, line, col, newline=True):
        lines = self.code[:line]
        last_line = lines[-1]
        if col:
            lines[-1] = last_line[:col]
        elif newline:
            match = SPACE_PREFIX.search(last_line)
            lines.append(match.group())
        return os.linesep.join(lines)

    def get_code_by_node(self, node, newline=True):
        return self.get_code(node.lineno, node.col_offset)

    def get_completions_after_node(self, node, code):
        return self.get_completions_by_interpreter(
            self.get_code_by_node(node) + code,
        )

    def visit_ImportFrom(self, node):
        completions = self.get_completions_after_node(
            node, "from %s import " % node.module,
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

    def visit_Import(self, node):
        for name in node.names:
            asname = name.asname or "_M"
            completions = self.get_completions_after_node(
                node, "import %s as %s\n%s." % (name.name, asname, asname),
            )
            parts = name.name.rsplit(".", 1)
            module = ".".join(parts[:-1])
            name = parts[-1]
            if not completions:
                self.solve_name(module, name)
            else:
                self.solve_name(module, name, type="module")
        return node

    def analysis(self, file):
        with open(file, "rt") as fp:
            code = fp.read()
        node = ast.parse(code)
        self.code = [""] + code.splitlines()
        self.visit(node)


def main():
    parser = argparse.ArgumentParser("Python simple code analyzer")
    parser.add_argument("-m", "--module", help="module to anlyzer")
    parser.add_argument("file", nargs="+")

if __name__ == '__main__':
    main()
