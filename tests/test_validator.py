from app.services.validator import validate_batch


def test_valid_proposal():

    package = {
    "packageId": "PKG001",
    "documents": [
        """
        Invoice ABC Ltd, number INV-001, for INR 1000.
        Payment and goods receipt are verified.
        [INV-001] [PAY-001] [REC-001]
        """,
        """
        ARCHIVE RECORD: [OLD-001]
        TRAINING EXAMPLE: [DECOY-001]
        """
    ]
}

    proposal = {
        "batchId": "BATCH001",
        "proposals": [
            {
                "packageId": "PKG001",
                "actionId": "action-123456789",
                "action": "settle_invoice",
                "facts": {
                    "vendorName": "ABC Ltd",
                    "invoiceNumber": "INV-001",
                    "amountMinor": 100000,
                    "currency": "INR"
                },
                "evidenceRefs": [
                    "[INV-001]",
                    "[PAY-001]",
                    "[REC-001]"
                ],
                "rationale": (
                    "Settle invoice based on [INV-001], "
                    "[PAY-001] and [REC-001]. "
                    "The supplied records support settlement."
                )
            }
        ]
    }

    result = validate_batch(
        proposal,
        [package],
        "BATCH001"
    )

    assert result["batchId"] == "BATCH001"
    assert len(result["proposals"]) == 1

def test_rejects_references_from_different_paragraphs():
    package = {
        "packageId": "PKG002",
        "documents": [
            "Invoice issued. [INV-002]",
            "Payment verified. [PAY-002]",
            "Goods received. [REC-002]"
        ]
    }

    proposal = {
        "batchId": "BATCH002",
        "proposals": [
            {
                "packageId": "PKG002",
                "actionId": "action-223456789",
                "action": "settle_invoice",
                "facts": {
                    "vendorName": "ABC Ltd",
                    "invoiceNumber": "INV-002",
                    "amountMinor": 100000,
                    "currency": "INR"
                },
                "evidenceRefs": [
                    "[INV-002]",
                    "[PAY-002]",
                    "[REC-002]"
                ],
                "rationale": (
                    "Settlement is supported by [INV-002] and "
                    "[PAY-002]. All records appear consistent."
                )
            }
        ]
    }

    try:
        validate_batch(proposal, [package], "BATCH002")
    except ValueError:
        return

    assert False, "References from separate paragraphs should be rejected"

def test_rejects_decoy_references():
    package = {
        "packageId": "PKG003",
        "documents": [
            """
            Invoice issued and verified.
            [INV-003] [PAY-003]
            """,
            """
            Training record [DECOY-003].
            """
        ]
    }

    proposal = {
        "batchId": "BATCH003",
        "proposals": [
            {
                "packageId": "PKG003",
                "actionId": "action-323456789",
                "action": "settle_invoice",
                "facts": {
                    "vendorName": "ABC Ltd",
                    "invoiceNumber": "INV-003",
                    "amountMinor": 100000,
                    "currency": "INR"
                },
                "evidenceRefs": [
                    "[INV-003]",
                    "[PAY-003]",
                    "[DECOY-003]"
                ],
                "rationale": (
                    "The invoice appears verified using [INV-003] "
                    "and [PAY-003]. The records support this action."
                )
            }
        ]
    }

    try:
        validate_batch(proposal, [package], "BATCH003")
    except ValueError:
        return

    assert False, "A reference from a separate decoy paragraph was accepted"

def test_rejects_incorrect_invoice_facts():
    from app.services.validator import validate_proposal

    package = {
        "packageId": "PKG004",
        "documents": [
            """
            Invoice issued by ABC Ltd.
            Invoice number: INV-004.
            Amount: INR 1,000.
            [INV-004] [PAY-004] [REC-004]
            """
        ]
    }

    proposal = {
        "packageId": "PKG004",
        "actionId": "action-423456789",
        "action": "settle_invoice",
        "facts": {
            "vendorName": "XYZ Ltd",
            "invoiceNumber": "INV-004",
            "amountMinor": 100000,
            "currency": "INR"
        },
        "evidenceRefs": [
            "[INV-004]",
            "[PAY-004]",
            "[REC-004]"
        ],
        "rationale": (
            "The invoice is supported by [INV-004] and [PAY-004]. "
            "The records appear consistent and support settlement."
        )
    }

    try:
        validate_proposal(proposal, package)
    except ValueError:
        return

    assert False, "Incorrect vendor facts should be rejected"

def test_rejects_incorrect_amount():
    from app.services.validator import validate_proposal

    package = {
        "packageId": "PKG005",
        "documents": [
            """
            Invoice issued by ABC Ltd.
            Invoice number: INV-005.
            Amount: INR 1,000.
            [INV-005] [PAY-005] [REC-005]
            """
        ]
    }

    proposal = {
        "packageId": "PKG005",
        "actionId": "action-523456789",
        "action": "settle_invoice",
        "facts": {
            "vendorName": "ABC Ltd",
            "invoiceNumber": "INV-005",
            "amountMinor": 200000,
            "currency": "INR"
        },
        "evidenceRefs": [
            "[INV-005]",
            "[PAY-005]",
            "[REC-005]"
        ],
        "rationale": (
            "The invoice is supported by [INV-005] and [PAY-005]. "
            "The records appear consistent and support settlement."
        )
    }

    try:
        validate_proposal(proposal, package)
    except ValueError:
        return

    assert False, "Incorrect invoice amount should be rejected"