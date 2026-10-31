import json
import re
import uuid
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


ALLOWED_ACTIONS = {
    "settle_invoice",
    "request_approval",
    "hold_invoice",
    "reject_duplicate",
    "open_exception"
}


class InvoiceFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendorName: str = Field(min_length=1)
    invoiceNumber: str = Field(min_length=1)
    amountMinor: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class InvoiceProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packageId: str = Field(min_length=1)
    actionId: str = Field(min_length=12)
    action: Literal[
        "settle_invoice",
        "request_approval",
        "hold_invoice",
        "reject_duplicate",
        "open_exception"
    ]
    facts: InvoiceFacts
    evidenceRefs: list[str] = Field(min_length=3, max_length=3)
    rationale: str = Field(min_length=60, max_length=1500)


class ProposalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batchId: str = Field(min_length=1)
    proposals: list[InvoiceProposal]


def extract_paragraphs(package):
    paragraphs = []

    def collect(value):
        if isinstance(value, str):
            paragraphs.extend(
                paragraph.strip()
                for paragraph in re.split(r"\n\s*\n", value)
                if paragraph.strip()
            )
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(package.get("documents", []))
    return paragraphs

def extract_amount_and_currency(text):
    pattern = r"\b(INR|USD|EUR|GBP)\s*([\d,]+(?:\.\d{1,2})?)"
    matches = re.findall(pattern, text, re.IGNORECASE)

    values = []

    for currency, amount in matches:
        try:
            amount_minor = int(
                Decimal(amount.replace(",", "")) * 100
            )
            values.append((currency.upper(), amount_minor))
        except (InvalidOperation, ValueError):
            continue

    return values


def validate_proposal(proposal, package):
    proposal = InvoiceProposal.model_validate(proposal)

    if proposal.packageId != package.get("packageId"):
        raise ValueError("Package ID mismatch")

    if len(set(proposal.evidenceRefs)) != 3:
        raise ValueError("Evidence references must be unique")

    paragraphs = extract_paragraphs(package)

    evidence_paragraphs = [
        paragraph
        for paragraph in paragraphs
        if all(
            reference in paragraph
            for reference in proposal.evidenceRefs
        )
    ]

    if not evidence_paragraphs:
        raise ValueError("Evidence paragraph not found")

    evidence_text = " ".join(evidence_paragraphs)

    if proposal.facts.invoiceNumber not in evidence_text:
        raise ValueError("Invoice number does not match evidence")

    if proposal.facts.vendorName.casefold() not in evidence_text.casefold():
        raise ValueError("Vendor name does not match evidence")
    amounts = extract_amount_and_currency(evidence_text)

    expected_amount = (
        proposal.facts.currency,
        proposal.facts.amountMinor
    )

    if expected_amount not in amounts:
        raise ValueError("Invoice amount or currency does not match evidence")

    if not all(
        re.fullmatch(r"\[[A-Za-z0-9_-]+\]", reference)
        for reference in proposal.evidenceRefs
    ):
        raise ValueError("Evidence references must be bracketed references")

    if len(proposal.rationale.strip()) < 60:
        raise ValueError("Rationale is too short")

    if not all(
        reference in proposal.rationale
        for reference in proposal.evidenceRefs[:2]
    ):
        raise ValueError(
            "Rationale must cite at least two evidence references"
        )

    return proposal.model_dump(by_alias=True)


def validate_batch(data, packages, expected_batch_id):
    batch = ProposalBatch.model_validate(data)

    if batch.batchId != expected_batch_id:
        raise ValueError("Batch ID mismatch")

    expected_ids = [
        package.get("packageId")
        for package in packages
    ]

    if None in expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise ValueError("Invalid or duplicate package IDs")

    received_ids = [
        proposal.packageId
        for proposal in batch.proposals
    ]

    if (
        len(received_ids) != len(expected_ids)
        or set(received_ids) != set(expected_ids)
    ):
        raise ValueError("Proposal count or package IDs mismatch")

    action_ids = [
        proposal.actionId
        for proposal in batch.proposals
    ]

    if len(set(action_ids)) != len(action_ids):
        raise ValueError("Duplicate action IDs")

    package_map = {
        package["packageId"]: package
        for package in packages
    }

    validated = []

    for proposal in batch.proposals:
        validated.append(
            validate_proposal(
                proposal.model_dump(by_alias=True),
                package_map[proposal.packageId]
            )
        )

    return {
        "batchId": batch.batchId,
        "proposals": validated
    }