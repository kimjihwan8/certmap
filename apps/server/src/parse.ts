/**
 * 자연어 → 칩 (규칙 v0). 결정 일지 9·11·31번.
 *
 * "대전역 근처 싼 노포" → { 장소: 대전역, 칩: [착한가격, 백년가게] }
 * 가게를 찾는 게 아니라 칩을 채우기만 한다. 가게는 언제나 DB 에서 나온다 (LLM 이 가게를 지어낼 틈이 없다).
 *
 * 매칭 때와 같은 순서로 간다: 단어 사전 규칙을 먼저 만들고 → 사용자가 쓴 질문 정답지로 채점하고 →
 * 규칙이 못 푸는 몫이 크면 그때 LLM(Claude·Jev)과 비교한다. 이 파일이 그 기준선(v0)이다.
 *
 * 처리 순서 (단어 = 띄어쓰기로 나눈 덩어리):
 *   1. 반대 뜻 걸러내기   '비싼'은 '싼'을 품고 있지만 착한가격이 아니다 → 반영 못 한 조건으로
 *   2. '맛집'류          칩을 켜지 않는다. 정렬(실린 목록 수 순)이 곧 그 뜻이다 (결정 32번)
 *   2'. 사전             단어 안에 사전 낱말이 들어 있으면 그 칩 ('저렴한' ⊃ '저렴', '국밥집' ⊃ '국밥')
 *   3. 장소              '근처·주변·앞'과 조사를 뗀 단어가 상가 건물 이름과 정확히 같으면 장소 (결정 11번)
 *   4. 군말              '근처', '집', '식당'처럼 뜻을 바꾸지 않는 말은 버린다
 *   5. 나머지            반영 못 한 조건. 숨기지 않고 화면에 보여준다
 */
import type { CertFilter } from "./find.js";
import { type PlaceHit, searchPlaces } from "./search.js";

type Chip = { cert: CertFilter } | { cat: string };

// 사전: [단어 안에 들어 있으면, 칩, 화면에 보일 이름]. 위에 있는 것을 먼저 본다
const DICTIONARY: [string, Chip][] = [
  // 인증 (결정 9번 표)
  ["가성비", { cert: "good_price" }], ["저렴", { cert: "good_price" }], ["착한", { cert: "good_price" }], ["싼", { cert: "good_price" }],
  ["노포", { cert: "baengnyeon" }], ["오래된", { cert: "baengnyeon" }], ["전통", { cert: "baengnyeon" }], ["백년", { cert: "baengnyeon" }],
  ["깨끗", { cert: "hygiene" }], ["청결", { cert: "hygiene" }], ["위생", { cert: "hygiene" }], ["안심", { cert: "hygiene" }],
  ["모범", { cert: "mobum" }],
  ["LX", { cert: "lx" }], ["lx", { cert: "lx" }],   // 'LX 추천'처럼 콕 집어 말할 때만 LX 칩
  ["관광", { cert: "tour" }],
  // 업종 → 상가 소분류
  ["국밥", { cat: "국/탕/찌개류" }], ["해장국", { cat: "국/탕/찌개류" }], ["찌개", { cat: "국/탕/찌개류" }], ["감자탕", { cat: "국/탕/찌개류" }], ["설렁탕", { cat: "국/탕/찌개류" }], ["곰탕", { cat: "국/탕/찌개류" }],
  ["짜장", { cat: "중국집" }], ["짬뽕", { cat: "중국집" }], ["중국집", { cat: "중국집" }], ["중식", { cat: "중국집" }], ["탕수육", { cat: "중국집" }],
  ["칼국수", { cat: "국수/칼국수" }], ["국수", { cat: "국수/칼국수" }], ["수제비", { cat: "국수/칼국수" }],
  ["냉면", { cat: "냉면/밀면" }], ["밀면", { cat: "냉면/밀면" }],
  ["횟집", { cat: "횟집" }], ["회", { cat: "횟집" }],
  ["초밥", { cat: "일식 회/초밥" }], ["스시", { cat: "일식 회/초밥" }],
  ["돈가스", { cat: "일식 카레/돈가스/덮밥" }], ["돈까스", { cat: "일식 카레/돈가스/덮밥" }], ["덮밥", { cat: "일식 카레/돈가스/덮밥" }],
  ["삼겹살", { cat: "돼지고기 구이/찜" }], ["갈비", { cat: "돼지고기 구이/찜" }], ["고기", { cat: "돼지고기 구이/찜" }],
  ["한우", { cat: "소고기 구이/찜" }], ["소고기", { cat: "소고기 구이/찜" }],
  ["치킨", { cat: "치킨" }], ["통닭", { cat: "치킨" }],
  ["빵", { cat: "빵/도넛" }], ["베이커리", { cat: "빵/도넛" }],
  ["카페", { cat: "카페" }], ["커피", { cat: "카페" }],
  ["김밥", { cat: "김밥/만두/분식" }], ["분식", { cat: "김밥/만두/분식" }], ["떡볶이", { cat: "김밥/만두/분식" }], ["만두", { cat: "김밥/만두/분식" }],
  ["족발", { cat: "족발/보쌈" }], ["보쌈", { cat: "족발/보쌈" }],
  ["곱창", { cat: "곱창 전골/구이" }], ["막창", { cat: "곱창 전골/구이" }],
  ["피자", { cat: "피자" }], ["버거", { cat: "버거" }],
  ["백반", { cat: "백반/한정식" }], ["한정식", { cat: "백반/한정식" }], ["한식", { cat: "백반/한정식" }],
  ["마라", { cat: "마라탕/훠궈" }], ["훠궈", { cat: "마라탕/훠궈" }],
  ["쌀국수", { cat: "베트남식 전문" }], ["파스타", { cat: "파스타/스테이크" }], ["스테이크", { cat: "파스타/스테이크" }],
  ["닭갈비", { cat: "닭/오리고기 구이/찜" }], ["오리", { cat: "닭/오리고기 구이/찜" }],
  ["술집", { cat: "요리 주점" }], ["주점", { cat: "요리 주점" }], ["포차", { cat: "요리 주점" }],
];
// 사전 낱말을 품고 있지만 뜻이 다른 말. 사전보다 먼저 본다 ('비싼' ⊃ '싼', '회사' ⊃ '회')
const NOT_A_CHIP = ["비싼", "안싼", "회사", "회식", "고기집말고"];
// 장소 뒤에 붙는 말·조사. 떼고 나서 건물 이름과 비교한다
const PLACE_SUFFIX = /(근처|주변|인근|부근|앞|쪽|에서|에|의)+$/;
// '맛집'류: 칩을 켜지 않고 '여러 공공 목록에 실린 가게일수록 위'로 읽는다 (결정 32번).
// 예전에는 '맛집' → LX 칩이었는데, 그러면 LX 추천만 맛집이 된다 (사용자 지적)
const POPULAR = ["맛집", "맛있는", "유명", "인기", "추천"];
// 뜻을 바꾸지 않는 말
const FILLER = new Set(["근처", "주변", "인근", "부근", "앞", "쪽", "집", "곳", "데", "식당", "음식점", "가게", "좋은", "알려줘", "찾아줘", "어디", "있는", "에서", "곳은"]);

export interface ParseResult {
  place: PlaceHit | null;
  certs: CertFilter[];
  cats: string[];
  popular: boolean;                       // '맛집'류 말이 있었는지 (정렬은 원래 실린 목록 수 순이라 칩은 안 켠다)
  used: { word: string; as: string }[];   // 어느 단어를 무엇으로 읽었는지 (화면에 보여준다)
  unknown: string[];                      // 반영 못 한 말
}

export async function parseQuery(q: string): Promise<ParseResult> {
  const out: ParseResult = { place: null, certs: [], cats: [], popular: false, used: [], unknown: [] };
  const words = q.trim().split(/\s+/).filter(Boolean).slice(0, 12);
  for (const word of words) {
    if (NOT_A_CHIP.some((n) => word.includes(n))) {
      out.unknown.push(word);
      continue;
    }
    if (POPULAR.some((w) => word.includes(w))) {
      out.popular = true;
      out.used.push({ word, as: "popular" });
      continue;
    }
    const hit = DICTIONARY.find(([key]) => word.includes(key));
    if (hit) {
      const chip = hit[1];
      if ("cert" in chip && !out.certs.includes(chip.cert)) out.certs.push(chip.cert);
      if ("cat" in chip && !out.cats.includes(chip.cat)) out.cats.push(chip.cat);
      out.used.push({ word, as: "cert" in chip ? chip.cert : chip.cat });
      continue;
    }
    if (FILLER.has(word)) continue;
    if (!out.place) {
      const bare = word.replace(PLACE_SUFFIX, "");
      const places = bare.length >= 2 ? await searchPlaces(bare) : [];
      if (places.length) {
        out.place = places[0];               // 같은 이름의 건물이 여러 곳이면 가게가 많은 곳
        out.used.push({ word, as: "place" });
        continue;
      }
    }
    out.unknown.push(word);
  }
  return out;
}
