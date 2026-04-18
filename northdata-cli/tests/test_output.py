from __future__ import annotations

import io
import json
import sys

import pytest

from northdata_cli.output import print_json, print_pretty


def test_print_json_round_trips(capsys):
    print_json({"a": 1, "b": [1, 2]})
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": 1, "b": [1, 2]}


def test_print_json_unicode(capsys):
    print_json({"name": "Müller"})
    out = capsys.readouterr().out
    assert "Müller" in out


def test_print_pretty_dict_does_not_raise(capsys):
    print_pretty({"name": "Example", "nested": {"city": "Munich"}}, title="t")
    out = capsys.readouterr().out
    assert "Example" in out


def test_print_pretty_list_of_dicts(capsys):
    print_pretty([{"a": 1, "b": 2}, {"a": 3}], title="rows")
    out = capsys.readouterr().out
    # Rich renders the table; just confirm content lands
    assert "1" in out and "3" in out


def test_print_pretty_empty_list(capsys):
    print_pretty([], title="t")
    out = capsys.readouterr().out
    assert "empty" in out


def test_print_pretty_scalar(capsys):
    print_pretty("hello")
    # Rich falls back to print_json for non-dict/list
    out = capsys.readouterr().out
    assert out  # something was printed
