from datetime import timedelta

import base64
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs7

from cert_agent import certcheck
from conftest import CA, HOST, NOW, make_csr, new_key


@pytest.fixture(scope="module")
def pki():
    root = CA("Root")
    issuing = CA("Issuing", issuer=root)
    key = new_key()
    csr = make_csr(key)
    return {"root": root, "issuing": issuing, "key": key, "csr": csr, "leaf": issuing.sign(csr)}


def check(pki, certs, trusted=None, **kwargs):
    trusted = [pki["root"].cert] if trusted is None else trusted
    return certcheck.validate(pki["csr"], certs, trusted, now=NOW, **kwargs)


# ---------------------------------------------------------------- file formats

def test_reads_pem_der_p7b_and_bare_base64(pki):
    leaf, issuing = pki["leaf"], pki["issuing"].cert
    pem = (certcheck.to_pem(leaf) + certcheck.to_pem(issuing)).encode()
    der = leaf.public_bytes(serialization.Encoding.DER)
    assert len(certcheck.load_certificates(pem)) == 2
    assert certcheck.load_certificates(b"some text from the CA\n" + pem + b"\n")[0] == leaf
    assert certcheck.load_certificates(der) == [leaf]
    assert certcheck.load_certificates(base64.encodebytes(der)) == [leaf]
    for encoding in (serialization.Encoding.PEM, serialization.Encoding.DER):
        bundle = pkcs7.serialize_certificates([leaf, issuing], encoding)
        assert set(certcheck.load_certificates(bundle)) == {leaf, issuing}


@pytest.mark.parametrize("data", [b"", b"hello", b"-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n"])
def test_rejects_files_that_are_not_certificates(data):
    with pytest.raises(ValueError):
        certcheck.load_certificates(data)


def test_reads_csr_with_sap_style_header(pki):
    pem = certcheck.to_pem(pki["csr"]).replace("CERTIFICATE REQUEST", "NEW CERTIFICATE REQUEST").encode()
    assert certcheck.spki(certcheck.load_csr(pem)) == certcheck.spki(pki["csr"])
    assert certcheck.load_csr(pki["csr"].public_bytes(serialization.Encoding.DER)).subject == pki["csr"].subject
    with pytest.raises(ValueError):
        certcheck.load_csr(b"not a request")


# ---------------------------------------------------------------- validation

def test_good_certificate_passes(pki):
    result = check(pki, [pki["issuing"].cert, pki["leaf"]])  # order in the file does not matter
    assert result.ok and result.leaf == pki["leaf"]
    assert result.chain == [pki["issuing"].cert, pki["root"].cert]


def test_chain_may_end_at_an_allow_listed_issuing_ca(pki):
    result = check(pki, [pki["leaf"]], trusted=[pki["issuing"].cert])
    assert result.ok and result.chain == [pki["issuing"].cert]


def test_certificate_for_another_key_is_rejected(pki):
    other = pki["issuing"].sign(pki["csr"], public_key=new_key().public_key())
    result = check(pki, [other, pki["issuing"].cert])
    assert not result.ok and "key of the CSR" in result.problems[0]


def test_missing_intermediate_is_reported(pki):
    result = check(pki, [pki["leaf"]])
    assert not result.ok and "no issuing CA certificate" in result.problems[0]


def test_untrusted_ca_is_rejected(pki):
    rogue = CA("Rogue")
    result = check(pki, [rogue.sign(pki["csr"]), rogue.cert])
    assert not result.ok and "allow-list" in result.problems[0]


def test_forged_issuer_name_is_rejected(pki):
    fake = CA("Issuing")  # same name as the real issuing CA, different key
    result = check(pki, [fake.sign(pki["csr"]), pki["issuing"].cert])
    assert not result.ok and "no issuing CA certificate" in result.problems[0]


def test_issuer_without_ca_flag_is_rejected(pki):
    not_a_ca = CA("Server", issuer=pki["root"], is_ca=False)
    result = check(pki, [not_a_ca.sign(pki["csr"]), not_a_ca.cert])
    assert not result.ok


def test_expired_ca_is_rejected(pki):
    old = CA("Old Issuing", issuer=pki["root"], not_before=NOW - timedelta(days=800), days=700)
    result = check(pki, [old.sign(pki["csr"]), old.cert])
    assert not result.ok and "not valid today" in result.problems[0]


def test_validity_window(pki):
    issuing = pki["issuing"]
    short = check(pki, [issuing.sign(pki["csr"], days=20), issuing.cert])
    assert not short.ok and "expires too soon" in short.problems[0]
    assert check(pki, [issuing.sign(pki["csr"], days=20), issuing.cert], min_valid_days=5).ok
    future = check(pki, [issuing.sign(pki["csr"], not_before=NOW + timedelta(days=2)), issuing.cert])
    assert not future.ok and "not valid yet" in future.problems[0]


def test_names_must_be_covered(pki):
    issuing = pki["issuing"]
    wrong = check(pki, [issuing.sign(pki["csr"], names=["other.example.internal"]), issuing.cert])
    assert not wrong.ok and HOST in wrong.problems[0]
    assert check(pki, [issuing.sign(pki["csr"], names=["*.example.internal"]), issuing.cert]).ok
    extra = check(pki, [pki["leaf"], issuing.cert], extra_names=("alias.example.internal",))
    assert not extra.ok and "alias.example.internal" in extra.problems[0]


def test_csr_without_san_falls_back_to_common_name():
    key = new_key()
    assert certcheck.required_names(make_csr(key, cn=HOST, names=[])) == [HOST]
    assert certcheck.required_names(make_csr(key, cn="SID SSL server", names=[])) == []
