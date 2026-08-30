import pytest
pytest.importorskip('hypothesis')
from hypothesis import given, strategies as st
from apex.domain.rules import calculate_selling_price

@given(st.integers(35, 150), st.integers(35, 150))
def test_selling_price_never_exceeds_current_or_purchase_plus_half(purchase, current):
    sell = calculate_selling_price(purchase, current)
    assert sell <= current
    if current > purchase:
        assert sell == purchase + (current - purchase) // 2
    else:
        assert sell == current
