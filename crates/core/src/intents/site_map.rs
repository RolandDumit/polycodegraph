//! Conservative, bounded correspondence of exact source intervals. No ID remapping.
use crate::model::{Edge, language};
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OffsetUnit {
    Utf16,
    Bytes,
    CodePoints,
}
impl OffsetUnit {
    pub fn for_file(file: &str) -> Option<Self> {
        match language(file) {
            "dart" | "typescript" | "javascript" | "java" => Some(Self::Utf16),
            "go" => Some(Self::Bytes),
            "python" | "rust" | "swift" | "objectivec" | "kotlin" => Some(Self::CodePoints),
            _ => None,
        }
    }
    fn len(self, text: &str) -> usize {
        match self {
            Self::Utf16 => text.encode_utf16().count(),
            Self::Bytes => text.len(),
            Self::CodePoints => text.chars().count(),
        }
    }
}
#[derive(Debug, Serialize)]
pub struct Interval {
    pub before_start: usize,
    pub after_start: usize,
    pub length: usize,
    pub before_line: usize,
    pub after_line: usize,
}
#[derive(Default, Debug)]
pub struct SiteMap {
    pub intervals: Vec<Interval>,
    pub work: usize,
    pub limit: Option<&'static str>,
}
struct Line<'a> {
    text: &'a str,
    start: usize,
}
fn lines(text: &str, unit: OffsetUnit, allowance: usize) -> Option<Vec<Line<'_>>> {
    let mut result = vec![];
    let mut start = 0;
    for text in text.split_inclusive('\n') {
        if result.len() >= allowance {
            return None;
        }
        result.push(Line { text, start });
        start += unit.len(text);
    }
    Some(result)
}
impl SiteMap {
    pub fn new(before: &str, after: &str, unit: OffsetUnit, allowance: usize) -> Self {
        let mut map = Self::default();
        let Some(a) = lines(before, unit, allowance) else {
            map.limit = Some("source correspondence line budget exhausted");
            return map;
        };
        let Some(b) = lines(after, unit, allowance.saturating_sub(a.len())) else {
            map.limit = Some("source correspondence line budget exhausted");
            return map;
        };
        map.work = a.len() + b.len();
        let mut occurrences = BTreeMap::<&str, (Vec<usize>, Vec<usize>)>::new();
        for (i, line) in a.iter().enumerate() {
            occurrences.entry(line.text).or_default().0.push(i);
        }
        for (i, line) in b.iter().enumerate() {
            occurrences.entry(line.text).or_default().1.push(i);
        }
        let mut anchors: Vec<_> = occurrences
            .values()
            .filter(|(a, b)| a.len() == 1 && b.len() == 1)
            .map(|(a, b)| (a[0], b[0]))
            .collect();
        anchors.sort_unstable();
        if anchors.windows(2).any(|w| w[0].1 >= w[1].1) {
            map.limit = Some("reordered source anchors; site correspondence ambiguous");
            return map;
        }
        let mut left = (0, 0);
        for right in anchors
            .into_iter()
            .chain(std::iter::once((a.len(), b.len())))
        {
            let old = &a[left.0..right.0];
            let new = &b[left.1..right.1];
            if old.len() == new.len() {
                for (index, (old, new)) in old.iter().zip(new).enumerate() {
                    if map.work >= allowance {
                        map.limit = Some("source correspondence work budget exhausted");
                        return map;
                    }
                    map.work += 1;
                    if old.text == new.text {
                        map.intervals.push(Interval {
                            before_start: old.start,
                            after_start: new.start,
                            length: unit.len(old.text),
                            before_line: left.0 + index + 1,
                            after_line: left.1 + index + 1,
                        });
                    } else if right.0 - left.0 == 1 && right.1 - left.1 == 1 {
                        // Exact unique fragments within a changed line. Separators are
                        // only textual anchors, never a parser or whitespace equivalence.
                        let mut byte = 0;
                        for fragment in old.text.split_inclusive(';') {
                            let cost = old.text.len().saturating_add(new.text.len());
                            if cost > allowance.saturating_sub(map.work) {
                                map.limit = Some("source correspondence fragment budget exhausted");
                                break;
                            }
                            map.work += cost;
                            let needle = fragment.trim();
                            if !needle.is_empty()
                                && needle.ends_with(';')
                                && old.text.matches(needle).count() == 1
                                && new.text.matches(needle).count() == 1
                            {
                                let start = byte + fragment.find(needle).expect("substring");
                                let destination = new.text.find(needle).expect("matched fragment");
                                map.intervals.push(Interval {
                                    before_start: old.start + unit.len(&old.text[..start]),
                                    after_start: new.start + unit.len(&new.text[..destination]),
                                    length: unit.len(needle),
                                    before_line: left.0 + 1,
                                    after_line: left.1 + 1,
                                });
                            }
                            byte += fragment.len();
                        }
                    }
                }
            }
            if right.0 < a.len() {
                map.intervals.push(Interval {
                    before_start: a[right.0].start,
                    after_start: b[right.1].start,
                    length: unit.len(a[right.0].text),
                    before_line: right.0 + 1,
                    after_line: right.1 + 1,
                });
            }
            left = (right.0 + 1, right.1 + 1);
        }
        map.intervals.sort_by_key(|i| i.before_start);
        map
    }
    pub fn position(&self, edge: &Edge) -> Option<(usize, usize)> {
        let index = self
            .intervals
            .partition_point(|i| i.before_start <= edge.offset)
            .checked_sub(1)?;
        let range = &self.intervals[index];
        (edge.line == range.before_line && edge.offset - range.before_start < range.length).then(
            || {
                (
                    range.after_line,
                    range.after_start + edge.offset - range.before_start,
                )
            },
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn site(line: usize, offset: usize) -> Edge {
        Edge {
            source: "s".into(),
            target: "t".into(),
            kind: "calls".into(),
            file: "a.ts".into(),
            line,
            offset,
            confidence: "resolved".into(),
        }
    }
    #[test]
    fn original_units_and_crlf_are_preserved() {
        for unit in [OffsetUnit::Utf16, OffsetUnit::Bytes, OffsetUnit::CodePoints] {
            let before = "// 🦀\r\none();\r\ntwo();\r\n";
            let after = "// new 🦀\r\n// 🦀\r\none();\r\n// between\r\ntwo();\r\n";
            let map = SiteMap::new(before, after, unit, 100);
            let old = unit.len("// 🦀\r\n");
            let new = unit.len("// new 🦀\r\n// 🦀\r\n");
            assert_eq!(map.position(&site(2, old)), Some((3, new)));
            assert_eq!(
                map.position(&site(3, old + unit.len("one();\r\n"))),
                Some((5, new + unit.len("one();\r\n// between\r\n")))
            );
        }
    }
    #[test]
    fn duplicate_sites_are_not_arbitrarily_associated() {
        let map = SiteMap::new(
            "begin\n  call(); call();\nend\n",
            "begin\n  call();\nend\n",
            OffsetUnit::Utf16,
            100,
        );
        assert_eq!(map.position(&site(2, 8)), None);
        assert_eq!(map.position(&site(2, 16)), None);
        let map = SiteMap::new(
            "begin\n  call(1); call(2);\nend\n",
            "begin\n  call(2);\nend\n",
            OffsetUnit::Utf16,
            100,
        );
        assert_eq!(map.position(&site(2, 17)), Some((2, 8)));
    }
    #[test]
    fn reorders_and_exhaustion_are_explicit() {
        assert!(
            SiteMap::new("one\ntwo\n", "two\none\n", OffsetUnit::Utf16, 100)
                .limit
                .is_some()
        );
        assert!(
            SiteMap::new("one\ntwo\n", "one\ntwo\n", OffsetUnit::Utf16, 1)
                .limit
                .is_some()
        );
        let map = SiteMap::new(
            "begin\nsame\nsame\nend\n",
            "new\nbegin\nsame\nsame\nend\n",
            OffsetUnit::Utf16,
            100,
        );
        assert_eq!(map.position(&site(2, 6)), Some((3, 10)));
        assert_eq!(map.position(&site(3, 11)), Some((4, 15)));
    }
}
