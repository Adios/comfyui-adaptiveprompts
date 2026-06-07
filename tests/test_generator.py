import sys
import os
import pytest
import shutil

import types

node_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.modules["py"] = types.ModuleType("py")
sys.modules["py"].__path__ = [os.path.join(node_root, "py")]
sys.path.insert(0, node_root)

from py.generator import SeededRandom, resolve_wildcards, find_next_bracket_span, _split_top_level_pipes
from py.wildcard_utils import handle_conditional_branches

@pytest.fixture
def wildcard_dir(tmp_path):
    d = tmp_path / "wildcards"
    d.mkdir()
    yield str(d)
    if d.exists():
        shutil.rmtree(d)

def test_find_next_bracket_span():
    span = find_next_bracket_span("hello { a | { b | c } } world")
    assert span == (6, 22)

def test_lazy_evaluation(wildcard_dir):
    res = resolve_wildcards("{ a | { b | c } }", SeededRandom(0), wildcard_dir)
    assert res.strip() == "a"

def test_variable_assignment(wildcard_dir):
    res = resolve_wildcards("{hello}^varA { __^varA__ }", SeededRandom(0), wildcard_dir)
    assert res.strip() == "hello hello"

def test_switch_basic(wildcard_dir):
    prompt = "{switch(view)\n  | close-up: (face:1.2)\n  | full-body: shoes\n  | default: nothing\n  }"
    vars1 = {"view": {"origin": "close-up"}}
    res1 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars1)
    assert res1.strip() == "(face:1.2)"

    vars2 = {"view": {"origin": "unknown"}}
    res2 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars2)
    assert res2.strip() == "nothing"

def test_switch_lazy_default(wildcard_dir):
    prompt = "{switch(view)\n  | close-up: A\n  | default: { B | C }\n  }"
    vars1 = {"view": {"origin": "unknown"}}
    res1 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars1)
    assert res1.strip() in ["B", "C"]

def test_conditional_inside_wildcard_file(wildcard_dir):
    import os
    wildcard_path = os.path.join(wildcard_dir, "logic_test.txt")
    with open(wildcard_path, "w") as f:
        f.write("{switch(view) | close-up: inside-wildcard-yes | default: inside-wildcard-no}")

    vars1 = {"view": {"o1": "close-up"}}
    # Test with variable defined and matching
    res1 = resolve_wildcards("__logic_test__", SeededRandom(0), wildcard_dir, _resolved_vars=vars1)
    assert res1.strip() == "inside-wildcard-yes"

    # Test with variable undefined
    res2 = resolve_wildcards("__logic_test__", SeededRandom(0), wildcard_dir, _resolved_vars={})
    assert res2.strip() == "inside-wildcard-no"

def test_switch_complex_matching(wildcard_dir):
    prompt = "{switch(view)\n  | (small breasts: 0.8): A\n  | ~large: B\n  | default: C\n  }"
    
    # Test 1: exact match
    vars1 = {"view": {"o1": "(small breasts: 0.8)"}}
    res1 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars1)
    assert res1.strip() == "A"

    # Test 4: default
    vars4 = {"view": {"o1": "unknown"}}
    res4 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars4)
    assert res4.strip() == "C"

def test_lazy_evaluation_keyword_injection(wildcard_dir):
    # Keyword injection is NOT possible. The engine checks for `switch(...)` before resolving wildcards
    # in the choice itself. So `{ {__^my_keyword__} | Yes | No }` is treated as a standard roulette.
    vars1 = {"view": {"o1": "full body"}, "my_keyword": {"o1": "switch(view)"}}
    prompt = "{ {__^my_keyword__} | Yes | No }"
    
    # Run a few times to show it's just roulette picking between the 3 choices
    results = set()
    for i in range(10):
        res = resolve_wildcards(prompt, SeededRandom(i), wildcard_dir, _resolved_vars=vars1)
        results.add(res.strip())
        
    assert "switch(view)" in results
    assert "Yes" in results
    assert "No" in results

def test_inline_var_assignment(wildcard_dir):
    prompt = "I want to play <gametype={nintendo|video} game>, definitely __^gametype__"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "I want to play , definitely nintendo game"

def test_inline_flag_fallback(wildcard_dir):
    prompt = "<fruit=apples> <fruit??keeps doctor away>"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "keeps doctor away"

def test_if_condition(wildcard_dir):
    prompt = "<color=red> {if(color==red) | matches | default: doesnt_match}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "matches"

def test_if_condition_undefined(wildcard_dir):
    prompt = "{if(color) | defined | default: not_defined}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "not_defined"

def test_switch_fallthrough(wildcard_dir):
    prompt = "<color=red> {switch(color) | red | blue: yes | default: no}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "yes"

def test_switch_fallthrough_complex_with_lora(wildcard_dir):
    prompt = "<food=fruit> {switch(food) | fruit | vegetable: natural foods <lora:healthy:1.0> | candy | dessert: sweet treats <lora:sugar:0.8>}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "natural foods <lora:healthy:1.0>"

    prompt2 = "<food=candy> {switch(food) | fruit | vegetable: natural foods <lora:healthy:1.0> | candy | dessert: sweet treats <lora:sugar:0.8>}"
    res2 = resolve_wildcards(prompt2, SeededRandom(0), wildcard_dir)
    assert res2.strip() == "sweet treats <lora:sugar:0.8>"

def test_lora_ignored(wildcard_dir):
    prompt = "<lora:name:1.0> {switch(color) | red: a | blue: b}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "<lora:name:1.0>"

def test_lazy_evaluation_in_switch(wildcard_dir):
    prompt = "<color={red}> {switch(color) | red: YES | default: NO}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "YES"

def test_lazy_evaluation_in_if(wildcard_dir):
    prompt = "<color={blue}> {if(color==blue) | YES | default: NO}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "YES"

def test_switch_shortcut_with_lora(wildcard_dir):
    prompt = "<style=anime> {switch(style) | anime: <lora:anime:1.0> | <lora:photo:1.0>}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "<lora:anime:1.0>"

def test_assignment_containing_lora(wildcard_dir):
    prompt = "<mystyle=<lora:name:1.0>> {switch(mystyle) | <lora:name:1.0>: YES | default: NO}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "YES"

def test_flag_fallback_with_nested_wildcards(wildcard_dir):
    prompt = "<missing_flag??{a|b}>"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == ""

def test_flag_set_with_nested_wildcards(wildcard_dir):
    prompt = "<myflag> <myflag??{a|b}>"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() in ["a", "b"]

def test_if_multiple_values(wildcard_dir):
    prompt = "<color=green> {if(color==red|green|blue) | YES | default: NO}"
    res = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir)
    assert res.strip() == "YES"

def test_if_not_empty(wildcard_dir):
    # Pure flag is empty string, so it should fail the != empty check
    prompt1 = "<myflag> {if(myflag!=) | YES | default: NO}"
    res1 = resolve_wildcards(prompt1, SeededRandom(0), wildcard_dir)
    assert res1.strip() == "NO"

    # Assigned variable with spaces/newlines should be stripped and fail
    prompt2 = "<myvar=   \n  > {if(myvar!=) | YES | default: NO}"
    res2 = resolve_wildcards(prompt2, SeededRandom(0), wildcard_dir)
    assert res2.strip() == "NO"

    # Assigned variable with actual content should pass
    prompt3 = "<myvar=hello> {if(myvar!=) | YES | default: NO}"
    res3 = resolve_wildcards(prompt3, SeededRandom(0), wildcard_dir)
    assert res3.strip() == "YES"

def test_if_not_equal_value(wildcard_dir):
    prompt1 = "<color=red> {if(color!=blue) | YES | default: NO}"
    res1 = resolve_wildcards(prompt1, SeededRandom(0), wildcard_dir)
    assert res1.strip() == "YES"

    prompt2 = "<color=blue> {if(color!=blue) | YES | default: NO}"
    res2 = resolve_wildcards(prompt2, SeededRandom(0), wildcard_dir)
    assert res2.strip() == "NO"

def test_if_empty_function(wildcard_dir):
    # Should be true for undefined
    prompt1 = "{if(empty(missing)) | EMPTY | default: NOT_EMPTY}"
    res1 = resolve_wildcards(prompt1, SeededRandom(0), wildcard_dir)
    assert res1.strip() == "EMPTY"

    # Should be true for assigned but empty
    prompt2 = "<myvar=   > {if(empty(myvar)) | EMPTY | default: NOT_EMPTY}"
    res2 = resolve_wildcards(prompt2, SeededRandom(0), wildcard_dir)
    assert res2.strip() == "EMPTY"

    # Should be false for assigned and not empty
    prompt3 = "<myvar=hello> {if(empty(myvar)) | EMPTY | default: NOT_EMPTY}"
    res3 = resolve_wildcards(prompt3, SeededRandom(0), wildcard_dir)
    assert res3.strip() == "NOT_EMPTY"

def test_if_equal_empty_string(wildcard_dir):
    # if(var==) means checking if it equals empty string
    prompt1 = "<myvar=  > {if(myvar==) | EMPTY | default: NOT_EMPTY}"
    res1 = resolve_wildcards(prompt1, SeededRandom(0), wildcard_dir)
    assert res1.strip() == "EMPTY"

def test_paradox_undefined_variables(wildcard_dir):
    # Undefined variable should evaluate as empty string implicitly
    prompt1 = "{if(missing!=blue) | YES | default: NO}"
    res1 = resolve_wildcards(prompt1, SeededRandom(0), wildcard_dir)
    assert res1.strip() == "YES"

    # missing!=empty should be NO because it IS empty
    prompt2 = "{if(missing!=) | YES | default: NO}"
    res2 = resolve_wildcards(prompt2, SeededRandom(0), wildcard_dir)
    assert res2.strip() == "NO"

    # missing==empty should be YES because it IS empty
    prompt3 = "{if(missing==) | YES | default: NO}"
    res3 = resolve_wildcards(prompt3, SeededRandom(0), wildcard_dir)
    assert res3.strip() == "YES"



