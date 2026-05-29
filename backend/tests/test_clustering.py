import pytest
from app.pipeline.clustering import _select_top_examples

def test_select_top_examples_deduplication():
    # Test that identical text posts are deduplicated and only one makes it into the examples
    post_ids = ["post1", "post2", "post3", "post4"]
    
    post_by_id = {
        "post1": {"score": 100, "text": "This is a trend post!"},
        "post2": {"score": 90, "text": "This is a trend post!"}, # Duplicate text
        "post3": {"score": 80, "text": "Something completely different"},
        "post4": {"score": 70, "text": "THIS IS A TREND POST!"}, # Case insensitive duplicate
    }
    
    examples = _select_top_examples(post_ids, post_by_id, top_k=3)
    
    # post1 has highest score so it should be included
    # post2 has same text as post1, should be skipped
    # post3 has different text, should be included
    # post4 has same text (case diff), should be skipped
    
    assert len(examples) == 2
    assert "post1" in examples
    assert "post3" in examples
    assert "post2" not in examples
    assert "post4" not in examples

def test_select_top_examples_ranking():
    # Test that it properly picks the highest scored unique posts up to top_k
    post_ids = ["a", "b", "c", "d"]
    post_by_id = {
        "a": {"score": 10, "text": "Text A"},
        "b": {"score": 50, "text": "Text B"},
        "c": {"score": 30, "text": "Text C"},
        "d": {"score": 20, "text": "Text D"},
    }
    
    examples = _select_top_examples(post_ids, post_by_id, top_k=2)
    assert len(examples) == 2
    assert examples[0] == "b" # Highest score
    assert examples[1] == "c" # Second highest
