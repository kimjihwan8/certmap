# PostgreSQL + PostGIS(위치) + pgvector(의미 검색) 한 이미지. 결정 일지 20번.
#
# 공식 postgres 이미지에서 시작해 확장 두 개를 설치한다.
# postgis/postgis 이미지를 안 쓰는 이유: 그 이미지는 인텔(amd64)용만 있어 애플 실리콘 맥에서 느리게 돈다.
# 공식 postgres 이미지는 PostgreSQL 공식 apt 저장소가 이미 등록돼 있어, 확장을 패키지로 바로 받을 수 있다.
FROM postgres:17-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-17-postgis-3 postgresql-17-pgvector \
 && rm -rf /var/lib/apt/lists/*
