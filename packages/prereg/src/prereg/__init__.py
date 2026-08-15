"""Latent Imagination — prereg (pure governance lib; zero network, zero project imports)."""

from prereg.anchor_format import AnchorRecord, VerifyReport
from prereg.certificate import (
    BAR_FORMULA,
    BarInstantiation,
    Certificate,
    CertificateCitation,
    CertificateError,
    SignerRef,
    assemble_certificate,
    certificate_from_dict,
    compute_certificate_hash,
    currently_valid,
    verify_certificate_bytes,
)
from prereg.chain import (
    ChainManifest,
    PrecedenceVerdict,
    assemble_chain,
    verify_chain_precedence,
)
from prereg.verify import verify_offline

__all__ = [
    "BAR_FORMULA",
    "AnchorRecord",
    "BarInstantiation",
    "Certificate",
    "CertificateCitation",
    "CertificateError",
    "ChainManifest",
    "PrecedenceVerdict",
    "SignerRef",
    "VerifyReport",
    "assemble_certificate",
    "assemble_chain",
    "certificate_from_dict",
    "compute_certificate_hash",
    "currently_valid",
    "verify_certificate_bytes",
    "verify_chain_precedence",
    "verify_offline",
]
