/**
 * 문장 → 벡터(임베딩). 의미 검색용. 결정 일지 20·33·35번.
 *
 * DB 채우기(소개글 → 벡터, packages/db)와 서버(검색어 → 벡터, apps/server)가 반드시 같은 모델로 계산해야 한다.
 * 다른 모델로 만든 벡터끼리는 거리를 재도 의미가 없다. 그래서 이 패키지 하나를 두 곳이 같이 쓴다.
 *
 * 모델은 우리 서버 프로그램 안에서 돈다 (개발 중엔 이 맥, 배포하면 클라우드 서버). 키·비용이 없고 데이터가 밖으로 안 나간다.
 * 대신 모델이 클수록 서버 메모리를 많이 쓴다 → 비교 실험(sem_pool)에서 정확도와 메모리를 같이 잰다 (결정 35번).
 *
 * 서비스 기본 모델은 DEFAULT_MODEL. 실험에서만 다른 모델을 고른다.
 */
import { type FeatureExtractionPipeline, pipeline } from "@huggingface/transformers";

export interface ModelSpec {
  id: string;                         // Hugging Face 모델 이름 (ONNX 판)
  dim: number;                        // 벡터 길이
  pooling: "mean" | "cls";            // 낱말 벡터들을 문장 벡터 하나로 합치는 방법 (모델마다 학습한 방식대로 써야 한다)
  prefix: { query: string; passage: string };   // 질문·문서 앞에 붙일 말 (모델 사용법)
  sizeMb: number;                     // int8 판 파일 크기
}

export const MODELS = {
  // e5 계열: 앞에 'query: ' / 'passage: ' 를 붙여야 제 성능이 난다. 짧은 질문과 긴 문서를 구별해 주면 더 잘 맞춘다
  "e5-small": { id: "Xenova/multilingual-e5-small", dim: 384, pooling: "mean", prefix: { query: "query: ", passage: "passage: " }, sizeMb: 118 },
  "e5-base": { id: "Xenova/multilingual-e5-base", dim: 768, pooling: "mean", prefix: { query: "query: ", passage: "passage: " }, sizeMb: 279 },
  // bge-m3: 한국어 포함 100여 개 언어. 앞말 없이 쓰고, 문장 벡터는 첫 낱말([CLS]) 자리 벡터를 쓴다 (모델 설명서)
  "bge-m3": { id: "Xenova/bge-m3", dim: 1024, pooling: "cls", prefix: { query: "", passage: "" }, sizeMb: 570 },
} satisfies Record<string, ModelSpec>;

export type ModelKey = keyof typeof MODELS;
export const DEFAULT_MODEL: ModelKey = "e5-small";
// 예전 이름 (DB 채우기·서버가 쓰는 기본 모델)
export const EMBED_MODEL = MODELS[DEFAULT_MODEL].id;
export const EMBED_DIM = MODELS[DEFAULT_MODEL].dim;

const loaded = new Map<ModelKey, Promise<FeatureExtractionPipeline>>();

/** 모델은 처음 쓸 때 한 번만 불러온다 (불러오기에 몇 초 걸린다). int8 양자화 판을 쓴다 */
function model(key: ModelKey): Promise<FeatureExtractionPipeline> {
  if (!loaded.has(key)) {
    loaded.set(key, pipeline("feature-extraction", MODELS[key].id, { dtype: "q8" }) as Promise<FeatureExtractionPipeline>);
  }
  return loaded.get(key)!;
}

/** 여러 문장을 한 번에. normalize = 길이 1로 맞춤 (그래야 코사인 거리로 비교할 수 있다) */
async function embed(key: ModelKey, texts: string[]): Promise<number[][]> {
  const out = await (await model(key))(texts, { pooling: MODELS[key].pooling, normalize: true });
  return out.tolist() as number[][];
}

/** 가게 소개글 같은 '찾아질 문서' */
export function embedPassages(texts: string[], key: ModelKey = DEFAULT_MODEL): Promise<number[][]> {
  return embed(key, texts.map((t) => MODELS[key].prefix.passage + t));
}

/** 사용자 검색어 */
export async function embedQuery(text: string, key: ModelKey = DEFAULT_MODEL): Promise<number[]> {
  return (await embed(key, [MODELS[key].prefix.query + text]))[0];
}

/** pgvector 에 넣을 글자 모양 '[0.1,0.2,…]' */
export function toVectorLiteral(v: number[]): string {
  return "[" + v.map((x) => x.toFixed(6)).join(",") + "]";
}
