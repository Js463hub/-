"""Build dict.json for pronounce.html from open word lists.

Sources (download them first):
  cmudict.dict             https://github.com/cmusphinx/cmudict           (BSD)  -> US IPA
  britfone.main.3.0.1.csv  https://github.com/JoseLlarena/Britfone        (MIT)  -> UK IPA
  ecdict.csv               https://github.com/skywind3000/ECDICT          (MIT)  -> 中文释义, 考试标签, 词形

Usage: python3 tools/build_dict.py CMUDICT BRITFONE ECDICT OUT_JSON
"""
import csv
import json
import re
import sys

csv.field_size_limit(10**9)

ARPA = {
    "AA": "ɑː", "AE": "æ", "AO": "ɔː", "AW": "aʊ", "AY": "aɪ", "EH": "e", "EY": "eɪ",
    "IH": "ɪ", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ",
    "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "r", "S": "s",
    "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
VOWELS = {"ɑː", "æ", "ɔː", "aʊ", "aɪ", "e", "eɪ", "ɪ", "oʊ", "ɔɪ", "ʊ", "ʌ", "ə", "ɚ", "ɝː",
          "i", "iː", "u", "uː", "əʊ", "ɒ", "ɜː", "ɪə", "eə", "ʊə", "ɑːr", "ɔːr"}

# Legal English syllable onsets, used to put the stress mark at the start of a syllable.
ONSETS = {()} | {(c,) for c in "p b t d k ɡ f v θ ð s z ʃ ʒ h tʃ dʒ m n l r w j".split()}
for a in "p b t d k ɡ f θ ʃ".split(): ONSETS.add((a, "r"))
for a in "p b k ɡ f s".split(): ONSETS.add((a, "l"))
for a in "p t k m n f".split(): ONSETS.add(("s", a))
for a in "t d k ɡ θ s h".split(): ONSETS.add((a, "w"))
for a in "p b t d k ɡ f v m n h l s".split(): ONSETS.add((a, "j"))
ONSETS |= {("s", "p", "r"), ("s", "t", "r"), ("s", "k", "r"), ("s", "p", "l"), ("s", "k", "w"),
           ("s", "p", "j"), ("s", "t", "j"), ("s", "k", "j")}


def place_stress(phones):
    """phones: list of (ipa, stress) with stress in {None, 1, 2}. Returns IPA string."""
    out = [p for p, _ in phones]
    marks = {}
    vowel_idx = [i for i, (p, _) in enumerate(phones) if p in VOWELS]
    prev_v = -1
    for vi in vowel_idx:
        s = phones[vi][1]
        if s:
            start = vi
            while start - 1 > prev_v and tuple(out[start - 1:vi]) in ONSETS:
                start -= 1
            marks[start] = "ˈ" if s == 1 else "ˌ"
        prev_v = vi
    return "".join(marks.get(i, "") + p for i, p in enumerate(out))


def cmu_to_ipa(tokens):
    phones = []
    n_stressed = sum(1 for t in tokens if t[-1] in "12")
    for t in tokens:
        base, st = (t[:-1], int(t[-1])) if t[-1].isdigit() else (t, None)
        if base == "AH": ipa = "ə" if st == 0 else "ʌ"
        elif base == "ER": ipa = "ɚ" if st == 0 else "ɝː"
        elif base == "IY": ipa = "i" if st == 0 else "iː"
        elif base == "UW": ipa = "u" if st == 0 else "uː"
        else: ipa = ARPA[base]
        stress = st if st in (1, 2) else None
        if n_stressed == 1 and len(tokens) <= 3: stress = None  # 单音节词不标重音
        phones.append((ipa, stress))
    if sum(1 for p, _ in phones if p in VOWELS) <= 1:
        phones = [(p, None) for p, _ in phones]
    return place_stress(phones)


BRIT = {"ɹ": "r", "ɛ": "e", "ɐ": "ʌ", "ɛə": "eə", "g": "ɡ"}


def brit_to_ipa(tokens):
    phones = []
    for t in tokens:
        st = None
        if t[0] in "ˈˌ":
            st, t = (1 if t[0] == "ˈ" else 2), t[1:]
        phones.append((BRIT.get(t, t), st))
    if sum(1 for p, _ in phones if p in VOWELS) <= 1:
        phones = [(p, None) for p, _ in phones]
    return place_stress(phones)


def load_variants(path, parse):
    d = {}
    for word, ipa in parse(path):
        key = re.sub(r"\(\d+\)$", "", word).lower()
        lst = d.setdefault(key, [])
        if ipa not in lst and len(lst) < 2:
            lst.append(ipa)
    return d


def parse_cmu(path):
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if line:
            w, *toks = line.split()
            yield w, cmu_to_ipa(toks)


def parse_brit(path):
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if ", " in line:
            w, p = line.split(", ", 1)
            yield w, brit_to_ipa(p.split())


def ecdict_uk(ph):
    """Best-effort conversion of ECDICT's older (Jones-style) British notation to modern IPA."""
    ph = ph.strip().replace("\xa0", "")
    if not ph or re.search(r"[()\\;^?@ \-yc]", ph):
        return ""
    for a, b in [("\u04d9", "ə"), ("є", "e"), ("ε", "e"), ("ɛ", "e"), ("'", "ˈ"), (",", "ˌ"), (".", "ˌ"),
                 (":", "ː"), ("g", "ɡ"), ("ɚ", "ə"), ("ɝ", "ɜː"), ("ɒː", "ɔː"), ("əː", "ɜː"),
                 ("əu", "əʊ"), ("ou", "əʊ"), ("ai", "aɪ"), ("ei", "eɪ"), ("ɔi", "ɔɪ"), ("ɒi", "ɔɪ"),
                 ("au", "aʊ"), ("iə", "ɪə"), ("uə", "ʊə"), ("o", "ɒ")]:
        ph = ph.replace(a, b)
    out = []
    for i, ch in enumerate(ph):
        nxt = ph[i + 1] if i + 1 < len(ph) else ""
        if ch == "i" and nxt != "ː":
            ch = "i" if nxt == "" else "ɪ"
        elif ch == "u" and nxt != "ː":
            ch = "ʊ"
        elif ch == "ɔ" and nxt not in ("ː", "ɪ"):
            ch = "ɒ"
        out.append(ch)
    ph = "".join(out).replace("ɒʊ", "əʊ")
    return ph if re.fullmatch(r"[a-zæðŋθʃʒʌəɑɒɔɪʊɜɡˈˌː]+", ph) else ""


def clean_translation(t):
    lines = [l.strip() for l in t.replace("\\n", "\n").split("\n") if l.strip()]
    main = [l for l in lines if not l.startswith("[网络]")] or lines
    out = []
    for l in main[:3]:
        if len(l) > 46:
            l = l[:46].rsplit(",", 1)[0] + "…"
        out.append(l)
    return "\n".join(out)


TAGS = ["zk", "gk", "cet4", "cet6", "ky", "ielts", "toefl", "gre"]


def main(cmu_path, brit_path, ec_path, out_path):
    us = load_variants(cmu_path, parse_cmu)
    uk = load_variants(brit_path, parse_brit)
    words = {}
    forms = {}
    with open(ec_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            w = row["word"]
            if not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", w):
                continue
            frq, bnc = int(row["frq"] or 0), int(row["bnc"] or 0)
            tag = row["tag"].split()
            common = (0 < frq <= 30000) or (0 < bnc <= 30000) or tag or row["oxford"] == "1" \
                or (row["collins"] or "0") != "0"
            if not common or not row["translation"].strip():
                continue
            key = w.lower()
            if key in words and words[key][0] == key:
                continue  # 优先保留小写词条
            ex = "/".join(p for p in row["exchange"].split("/") if p[:2] in ("p:", "d:", "i:", "3:", "s:", "r:", "t:"))
            rank = min(x for x in (frq, bnc, 99999) if x > 0)
            words[key] = [w, " · ".join(us.get(key, [])), " · ".join(uk.get(key, [])) or ecdict_uk(row["phonetic"]),
                          clean_translation(row["translation"]),
                          " ".join(TAGS.index(t).__str__() for t in tag if t in TAGS), ex, rank]
            for part in ex.split("/"):
                if ":" in part:
                    for fw in part[2:].split(","):
                        forms.setdefault(fw.lower(), key)
    # IPA for inflected forms that aren't headwords (went, children, ...)
    form_ipa = {}
    for fw, lemma in forms.items():
        if fw in words or fw == lemma:
            continue
        a, b = " · ".join(us.get(fw, [])), " · ".join(uk.get(fw, []))
        if a or b:
            form_ipa[fw] = [lemma, a, b]
    data = {"v": 1, "words": {k: v[1:] if v[0] == k else v[1:] + [v[0]] for k, v in words.items()},
            "forms": form_ipa}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(words)} words, {len(form_ipa)} forms; "
          f"US IPA {sum(1 for v in words.values() if v[1])}, UK IPA {sum(1 for v in words.values() if v[2])}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
