import sys
import os
import pytest
import shutil

# Remove the pytest 'py' module to avoid naming collision
if 'py' in sys.modules:
    del sys.modules['py']

# Add the root directory to the python path so 'py' acts as a package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
    res1 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars1, enable_conditionals=True)
    assert res1.strip() == "(face:1.2)"

    vars2 = {"view": {"origin": "unknown"}}
    res2 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars2, enable_conditionals=True)
    assert res2.strip() == "nothing"

def test_switch_lazy_default(wildcard_dir):
    prompt = "{switch(view)\n  | close-up: A\n  | default: { B | C }\n  }"
    vars1 = {"view": {"origin": "unknown"}}
    res1 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars1, enable_conditionals=True)
    assert res1.strip() in ["B", "C"]

def test_conditional_toggle_opt_in(wildcard_dir):
    # When enable_conditionals=False (default), it should treat {switch...} as a standard random choice
    prompt = "{switch(view) | Yes | No}"
    vars1 = {"view": {"origin": "Yes"}}
    
    results = set()
    for i in range(20):
        res = resolve_wildcards(prompt, SeededRandom(i), wildcard_dir, _resolved_vars=vars1, enable_conditionals=False)
        results.add(res.strip())
    
    assert "switch(view)" in results
    assert "Yes" in results
    assert "No" in results

def test_conditional_inside_wildcard_file(wildcard_dir):
    import os
    wildcard_path = os.path.join(wildcard_dir, "logic_test.txt")
    with open(wildcard_path, "w") as f:
        f.write("{switch(view) | close-up: inside-wildcard-yes | default: inside-wildcard-no}")

    vars1 = {"view": {"o1": "close-up"}}
    # Test with variable defined and matching
    res1 = resolve_wildcards("__logic_test__", SeededRandom(0), wildcard_dir, _resolved_vars=vars1, enable_conditionals=True)
    assert res1.strip() == "inside-wildcard-yes"

    # Test with variable undefined
    res2 = resolve_wildcards("__logic_test__", SeededRandom(0), wildcard_dir, _resolved_vars={}, enable_conditionals=True)
    assert res2.strip() == "inside-wildcard-no"

def test_switch_complex_matching(wildcard_dir):
    prompt = "{switch(view)\n  | (small breasts: 0.8): A\n  | ~large: B\n  | default: C\n  }"
    
    # Test 1: exact match
    vars1 = {"view": {"o1": "(small breasts: 0.8)"}}
    res1 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars1, enable_conditionals=True)
    assert res1.strip() == "A"

    # Test 4: default
    vars4 = {"view": {"o1": "unknown"}}
    res4 = resolve_wildcards(prompt, SeededRandom(0), wildcard_dir, _resolved_vars=vars4, enable_conditionals=True)
    assert res4.strip() == "C"

def test_lazy_evaluation_keyword_injection(wildcard_dir):
    # Keyword injection is NOT possible. The engine checks for `switch(...)` before resolving wildcards
    # in the choice itself. So `{ {__^my_keyword__} | Yes | No }` is treated as a standard roulette.
    vars1 = {"view": {"o1": "full body"}, "my_keyword": {"o1": "switch(view)"}}
    prompt = "{ {__^my_keyword__} | Yes | No }"
    
    # Run a few times to show it's just roulette picking between the 3 choices
    results = set()
    for i in range(10):
        res = resolve_wildcards(prompt, SeededRandom(i), wildcard_dir, _resolved_vars=vars1, enable_conditionals=True)
        results.add(res.strip())
        
    assert "switch(view)" in results
    assert "Yes" in results
    assert "No" in results
