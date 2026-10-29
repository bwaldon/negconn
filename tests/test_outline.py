import pandas as pd

from negconj.outline import sentence_breaks, unit_outline

# 8 U.S.C. § 1225(b)(2)(B), as extracted (units and elements tables).
B = "/us/usc/t8/s1225/b/2/B"
B_ELEMENTS = pd.DataFrame({
    "identifier": [B, B + "/i", B + "/ii", B + "/iii"],
    "text": ["Subparagraph (A) shall not apply to an alien—", "who is a crewman,",
             "to whom paragraph (1) applies, or", "who is a stowaway."]})
B_PARSE = ("Subparagraph (A) shall not apply to an alien— who is a crewman, to whom paragraph (1) "
           "applies, or who is a stowaway.")
B_DISPLAY = ("Subparagraph (A) shall not apply to an alien— (i) who is a crewman, (ii) to whom "
             "paragraph (1) applies, or (iii) who is a stowaway.")


def test_outline_depths_and_labels():
    ol = unit_outline(B, B_PARSE, B_DISPLAY, B_ELEMENTS)
    assert [(d, lab) for _, _, d, lab in ol] == [(0, ""), (1, "(i)"), (1, "(ii)"), (1, "(iii)")]
    assert [B_PARSE[s:e] for s, e, _, _ in ol] == list(B_ELEMENTS["text"])


def test_level_opening_into_sublevel_and_continuation():
    u = "/us/usc/t1/s1/a"
    els = pd.DataFrame({"identifier": [u, u + "/A/i", u + "/A/ii", u + "/B", u],
                        "text": ["The term means—", "x;", "y; and", "z,", "as the case may be."]})
    parse = "The term means— x; y; and z, as the case may be."
    display = "The term means— (A) (i) x; (ii) y; and (B) z, as the case may be."
    ol = unit_outline(u, parse, display, els)
    assert [(d, lab) for _, _, d, lab in ol] == [(0, ""), (1, "(A) (i)"), (2, "(ii)"), (1, "(B)"), (0, "")]


def test_no_outline_without_identifiers():
    els = B_ELEMENTS.assign(identifier=[B, None, B + "/ii", B + "/iii"])
    assert unit_outline(B, B_PARSE, B_DISPLAY, els) is None


def test_sentence_breaks_on_words():
    ol = unit_outline(B, B_PARSE, B_DISPLAY, B_ELEMENTS)
    words = B_PARSE.replace("—", " —").replace(",", " ,").replace(".", " .").replace("(", "( ").replace(")", " )").split()
    br = sentence_breaks(ol, B_PARSE, B_PARSE, words)
    assert [b[1:] for b in br] == [[0, ""], [1, "(i)"], [1, "(ii)"], [1, "(iii)"]]
    assert [words[b[0]] for b in br] == ["Subparagraph", "who", "to", "who"]


def test_sentence_inside_one_item_and_flat_units():
    ol = unit_outline(B, B_PARSE, B_DISPLAY, B_ELEMENTS)
    assert sentence_breaks(ol, B_PARSE, "to whom paragraph (1) applies, or",
                           ["to", "whom", "paragraph", "(", "1", ")", "applies", ",", "or"]) == [[0, 1, "(ii)"]]
    assert sentence_breaks(None, B_PARSE, B_PARSE, B_PARSE.split()) == []
    assert sentence_breaks(ol, B_PARSE, "Subparagraph (A) shall not", ["Subparagraph", "(", "A", ")", "shall", "not"]) == []
