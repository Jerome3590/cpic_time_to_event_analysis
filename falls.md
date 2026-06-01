<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# yes

Here’s a concrete inclusion/exclusion spec you can hand to an engineer for labeling “any fall‑related injury” encounters.

## 1. High‑level label definition

**Outcome name:** `fall_injury_any`
**Unit:** encounter (or claim line‑grouped encounter)

Set `fall_injury_any = 1` if, for a given encounter:

1. There is at least one **injury diagnosis** code in specific S00–T88 ranges (see below), and
2. There is at least one **external cause code for falls** in W00–W19 on the same encounter.[^1][^2][^3][^4]

Otherwise set `fall_injury_any = 0`.

## 2. Injury diagnosis code ranges (ICD‑10‑CM)

Use **ICD‑10‑CM Chapter 19, S00–T88**, but restrict to “injury/trauma” ranges and exclude poisonings/adverse effects if you only want physical injuries.[^5][^6][^7][^1]

Inclusion (any of the following as a diagnosis on the encounter):

- S00–S99: All injuries to specific body regions (head, neck, thorax, abdomen, extremities, etc.).[^7][^1][^5]
- T07: Unspecified multiple injuries.[^1][^7]
- T14: Injury of unspecified body region.[^7][^1]
- T20–T32: Burns and corrosions.[^1][^7]
- T33–T34: Frostbite.[^7][^1]
- T79: Certain early complications of trauma (e.g., traumatic shock, compartment syndrome) if you want to count downstream trauma manifestations as part of the fall injury episode.[^8][^9][^1]

Optional, depending on your research focus:

- **Include** T36–T65 (poisoning, toxic effects) only if you consider medication‑related injuries from falls in scope; most fall‑injury algorithms treat these separately.[^10][^1]
- **Exclude** T80–T88 (complications of surgical and medical care) if you want to focus on mechanical injuries from falls, not iatrogenic complications.[^10][^1]

Sequencing note: coding guidance typically sequences the injury (Sxx/Txx) as primary and the external cause as secondary, but for labeling you only care that both appear on the encounter.[^6][^3][^1]

### Optional incident‑only filter

If you want only **new** injuries:

- Restrict to diagnosis codes with **7th character = ‘A’** (initial encounter) and exclude codes with 7th character ‘D’ (subsequent) or ‘S’ (sequela).[^11][^6]


## 3. External cause fall codes (W00–W19)

Require **at least one** ICD‑10‑CM code in **W00–W19** on the same encounter.[^2][^4][^5]

This includes, for example:

- W00: Fall due to ice and snow.[^4]
- W01: Fall on same level from slipping, tripping and stumbling.[^12][^4]
- W03: Other fall on same level due to collision with another person.[^4]
- W06: Fall from bed.[^13][^14]
- W10: Fall on and from stairs and steps.[^14][^4]
- W11: Fall on and from ladder.[^14][^4]
- W17: Other fall from one level to another.[^14]
- W18: Other slipping, tripping and stumbling.[^12][^4]
- W19: Unspecified fall.[^15][^4]

Implementation rule:

- External cause codes live in the **V00–Y99** range; your engineer can filter any diagnosis on the encounter where `code >= 'W00' and code <= 'W19'` (string‑wise, after normalizing format) as meeting the fall mechanism requirement.[^2][^4][^1]

Again, for incident events you may optionally require:

- W00–W19 codes with **7th character ‘A’** (e.g., `W19.XXXA`) to focus on initial encounters for the fall event.[^16][^11][^15]


## 4. Explicit inclusion/exclusion logic

### 4.1. Include as fall‑related injury (pseudocode)

```text
For each encounter E:

  has_injury = any dx_code in:
      S00–S99 OR
      T07 OR
      T14 OR
      T20–T32 OR
      T33–T34 OR
      T79
      [plus optionally selected T36–T65]

  has_fall_ecode = any dx_code in W00–W19

  # Optional: only initial encounters
  if incident_only:
      has_injury = has_injury AND any corresponding injury codes with 7th char 'A'
      has_fall_ecode = has_fall_ecode AND any W00–W19 code with 7th char 'A'

  fall_injury_any = 1 if has_injury AND has_fall_ecode else 0
```


### 4.2. Explicit exclusions (recommended)

On the **outcome side** (not as features):

- Do **not** use R29.6 (repeated falls / tendency to fall) as part of the outcome label; treat as feature.[^3][^17]
- Do **not** use Z91.81 (history of falling) as part of the outcome; treat as feature.[^18][^19]
- Do **not** use CPT 1100F/1101F fall risk screening codes as outcome. They are process measures, not injuries.[^20]
- Exclude encounters where the only S00–T88 codes are clearly non‑injury consequences if you prefer (e.g., some T80–T88 surgical complications, pure poisoning codes if out of scope).[^10][^1]


## 5. Auxiliary flags for analysis

You might also ask your engineer to compute:


| Flag name | Definition |
| :-- | :-- |
| `fall_injury_any` | As above (injury S00–T88 subset + W00–W19) [^3][^4][^1] |
| `fall_injury_serious` | `fall_injury_any = 1` AND any fracture code T02.*, S12.*, S22.*, S32.*, S42.*, S52.*, S62.*, S72.*, S82.*, S92.* [^21][^1] |
| `fall_injury_head` | `fall_injury_any = 1` AND any S00–S09 (head injuries) [^5][^1] |

These let you build one model for `fall_injury_any` but still explore feature drivers by severity and body region.

***

If you share your data structure (e.g., single claims table vs. separate diagnosis and encounter tables, and whether codes are already normalized with dots/7th characters), I can translate this into SQL or PySpark you can drop in directly.
<span style="display:none">[^22][^23][^24][^25][^26][^27]</span>

<div align="center">⁂</div>

[^1]: https://www.allzonems.com/blogs/icd-10-cm-s00-t88-codes-injury-poisoning-guide/

[^2]: https://www.cdc.gov/nchs/injury/injury_matrices.htm

[^3]: https://codingintel.com/diagnosis-coding-for-fall/

[^4]: https://www.aapc.com/codes/icd-10-codes-range/V00-Y99/V00-X58/W00-X58/W00-W19/

[^5]: https://www.aapc.com/codes/icd-10-codes-range/S00-T88/

[^6]: https://ftp.cdc.gov/pub/health_statistics/nchs/publications/ICD10CM/2022/icd10cm-tabular-2022-April-1.pdf

[^7]: https://www.unboundmedicine.com/icd/view/ICD-10-CM/860517/5/S00_T88___Injury_poisoning_and_certain_other_consequences_of_external_causes

[^8]: https://www.aapc.com/codes/icd-10-codes/T79

[^9]: https://www.aapc.com/codes/icd-10-codes-range/S00-T88/T07-T88/T79-T79.A9XS/

[^10]: https://journal.ahima.org/Portals/0/archives/AHIMA files/Coding Injuries in ICD-10-CM.pdf

[^11]: https://basicmedicalkey.com/injury-and-certain-other-consequences-of-external-causes-and-external-causes-of-morbidity-icd-10-cm-chapter-19-codes-s00-t88-and-chapter-20-codes-v00-y99/

[^12]: https://hcmsus.com/blog/icd-10-codes-for-ground-level-fall

[^13]: https://www.healos.ai/icd10/w06

[^14]: https://www.chrisearley.com/blog/icd-10-codes-slip-and-fall-accidents/

[^15]: https://www.aapc.com/codes/icd-10-codes/W19

[^16]: https://prospecthealthcaresolutions.com/icd-10-code-for-ground-level-fall/

[^17]: https://yung-sidekick.com/blog/the-essential-guide-to-coding-frequent-falls-icd-10-(with-expert-tips)

[^18]: https://skriber.com/blog/z91-81-icd-10-code-for-history-of-falls

[^19]: https://www.sprypt.com/diagnosis/risk-for-falls

[^20]: https://www.vhan.com/dont-forget-to-prioritize-the-fall-risk-screening/

[^21]: https://doctormgt.com/ground-level-falls-ensuring-precision-in-diagnosis-and-care/

[^22]: https://www.cdc.gov/nchs/data/ice/ice95v1/c22.pdf

[^23]: https://icd.who.int/browse10/2019/en

[^24]: https://ibis.doh.nm.gov/resource/ICDCodesInjury.html

[^25]: http://medbox.iiab.me/modules/en-cdc/www.cdc.gov/nchs/injury/injury_matrices.htm

[^26]: https://www.cdc.gov/nchs/data/ice/10_diamatrix.pdf

[^27]: https://www.findacode.com/code-set.php?set=ICD10CM\&i=27173

