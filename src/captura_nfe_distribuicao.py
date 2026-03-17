#!/usr/bin/env python3
"""Captura DF-e de entrada (NF-e) via NFeDistribuicaoDFe usando certificado A1."""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import requests  # pyright: ignore[reportMissingModuleSource]
import yaml  # pyright: ignore[reportMissingModuleSource]
from requests_pkcs12 import Pkcs12Adapter  # pyright: ignore[reportMissingModuleSource]

NAMESPACE = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "nfe": "http://www.portalfiscal.inf.br/nfe",
}

ENDPOINTS = {
    "producao": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    "homologacao": "https://hom.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}


@dataclass
class Config:
    ambiente: str
    arquivo_pfx: str
    senha_pfx: str
    diretorio_base: Path
    estado_nsu_arquivo: Path
    timeout_segundos: int
    max_nsu_por_consulta: int
    cnpjs: list[str]


def carregar_config(caminho: Path) -> Config:
    with caminho.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    ambiente = raw["ambiente"].strip().lower()
    if ambiente not in ENDPOINTS:
        raise ValueError(f"Ambiente inválido: {ambiente}. Use 'producao' ou 'homologacao'.")

    return Config(
        ambiente=ambiente,
        arquivo_pfx=raw["certificado"]["arquivo_pfx"],
        senha_pfx=raw["certificado"]["senha"],
        diretorio_base=Path(raw["armazenamento"]["diretorio_base"]),
        estado_nsu_arquivo=Path(raw["armazenamento"]["estado_nsu_arquivo"]),
        timeout_segundos=int(raw["consulta"]["timeout_segundos"]),
        max_nsu_por_consulta=int(raw["consulta"]["max_nsu_por_consulta"]),
        cnpjs=[str(c).strip() for c in raw["cnpjs"]],
    )


def carregar_estado(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def salvar_estado(path: Path, estado: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def montar_xml_dist(cnpj: str, ult_nsu: str, ambiente: str) -> str:
    tp_amb = "1" if ambiente == "producao" else "2"
    return f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
<distDFeInt xmlns=\"http://www.portalfiscal.inf.br/nfe\" versao=\"1.01\">
    <tpAmb>{tp_amb}</tpAmb>
    <cUFAutor>91</cUFAutor>
    <CNPJ>{cnpj}</CNPJ>
    <distNSU>
        <ultNSU>{ult_nsu.zfill(15)}</ultNSU>
    </distNSU>
</distDFeInt>"""


def montar_soap(xml_dist: str) -> str:
    return f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
<soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\" xmlns:nfe=\"http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe\">
  <soap:Header/>
  <soap:Body>
    <nfe:nfeDistDFeInteresse>
      <nfe:nfeDadosMsg><![CDATA[{xml_dist}]]></nfe:nfeDadosMsg>
    </nfe:nfeDistDFeInteresse>
  </soap:Body>
</soap:Envelope>"""


def extrair_xml_retorno(conteudo: str) -> ET.Element:
    envelope = ET.fromstring(conteudo)
    dados_msg = envelope.find(".//nfe:nfeDistDFeInteresseResult", NAMESPACE)
    if dados_msg is None or not dados_msg.text:
        raise RuntimeError("Resposta SOAP não contém nfeDistDFeInteresseResult.")
    return ET.fromstring(dados_msg.text)


def salvar_docs_zip(dist_doc: ET.Element, destino_base: Path, cnpj: str) -> int:
    salvos = 0
    agora = datetime.now().strftime("%Y-%m")
    destino = destino_base / cnpj / agora
    destino.mkdir(parents=True, exist_ok=True)

    for doc_zip in dist_doc.findall(".//nfe:docZip", NAMESPACE):
        nsu = doc_zip.attrib.get("NSU", "sem_nsu")
        schema = doc_zip.attrib.get("schema", "desconhecido")
        conteudo_zip = base64.b64decode(doc_zip.text or "")
        xml_bytes = gzip.decompress(conteudo_zip)
        nome = f"{nsu}_{schema.replace('.', '_')}.xml"
        with (destino / nome).open("wb") as f:
            f.write(xml_bytes)
        salvos += 1

    return salvos


def consultar_distribuicao(session: requests.Session, config: Config, cnpj: str, ult_nsu: str) -> tuple[str, int]:
    xml_dist = montar_xml_dist(cnpj=cnpj, ult_nsu=ult_nsu, ambiente=config.ambiente)
    soap = montar_soap(xml_dist)

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse",
    }

    resposta = session.post(
        ENDPOINTS[config.ambiente],
        data=soap.encode("utf-8"),
        headers=headers,
        timeout=config.timeout_segundos,
    )
    resposta.raise_for_status()

    retorno = extrair_xml_retorno(resposta.text)
    cstat = retorno.findtext(".//nfe:cStat", default="", namespaces=NAMESPACE)
    xmotivo = retorno.findtext(".//nfe:xMotivo", default="", namespaces=NAMESPACE)

    if cstat not in {"137", "138"}:
        raise RuntimeError(f"SEFAZ retornou cStat={cstat}: {xmotivo}")

    ult_nsu_retorno = retorno.findtext(".//nfe:ultNSU", default=ult_nsu, namespaces=NAMESPACE)
    total_salvos = salvar_docs_zip(retorno, config.diretorio_base, cnpj)
    return ult_nsu_retorno, total_salvos


def criar_sessao(cert_path: str, cert_password: str) -> requests.Session:
    sessao = requests.Session()
    sessao.mount(
        "https://",
        Pkcs12Adapter(pkcs12_filename=cert_path, pkcs12_password=cert_password),
    )
    return sessao


def executar(config: Config) -> None:
    estado = carregar_estado(config.estado_nsu_arquivo)
    sessao = criar_sessao(config.arquivo_pfx, config.senha_pfx)

    for cnpj in config.cnpjs:
        ult_nsu = estado.get(cnpj, "0")
        total_cnpj = 0

        for _ in range(config.max_nsu_por_consulta):
            novo_nsu, salvos = consultar_distribuicao(sessao, config, cnpj, ult_nsu)
            total_cnpj += salvos
            if novo_nsu == ult_nsu:
                break
            ult_nsu = novo_nsu

        estado[cnpj] = ult_nsu
        print(f"[{cnpj}] Último NSU: {ult_nsu} | XMLs novos: {total_cnpj}")

    salvar_estado(config.estado_nsu_arquivo, estado)


def main() -> None:
    parser = argparse.ArgumentParser(description="Captura NF-e de entrada para CNPJs via distribuição DF-e")
    parser.add_argument("--config", required=True, help="Caminho do YAML de configuração")
    args = parser.parse_args()

    config = carregar_config(Path(args.config))
    os.makedirs(config.diretorio_base, exist_ok=True)
    executar(config)


if __name__ == "__main__":
    main()
