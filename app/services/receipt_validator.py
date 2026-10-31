
import json

def validate_continuation(task, message, data):
    if message.get("taskId") != task.task_id:
        raise ValueError("Task ID mismatch")

    if message.get("contextId") != task.context_id:
        raise ValueError("Context ID mismatch")

    if not isinstance(data, dict):
        raise ValueError("Invalid continuation data")

    if data.get("batchId") != task.batch_id:
        raise ValueError("Batch ID mismatch")

    results = data.get("results")

    if not isinstance(results, list):
        raise ValueError("Results must be a list")

    artifacts = json.loads(task.artifacts)
    proposal_artifacts = []

    for artifact in artifacts:
        for part in artifact.get("parts", []):
            if part.get("mediaType") == "application/vnd.ga5.invoice-action-proposals+json":
                proposal_artifacts.append(part.get("data"))

    if len(proposal_artifacts) != 1:
        raise ValueError("Expected exactly one proposal artifact")

    proposal_data = proposal_artifacts[0]

    if not isinstance(proposal_data, dict):
        raise ValueError("Invalid proposal artifact")

    if proposal_data.get("batchId") != task.batch_id:
        raise ValueError("Stored proposal batch mismatch")

    proposals = proposal_data.get("proposals")

    if not isinstance(proposals, list) or not proposals:
        raise ValueError("Invalid stored proposals")

    proposal_map = {}

    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ValueError("Invalid stored proposal")

        package_id = proposal.get("packageId")

        if not isinstance(package_id, str) or not package_id:
            raise ValueError("Invalid stored package ID")

        if package_id in proposal_map:
            raise ValueError("Duplicate stored package ID")

        if not isinstance(proposal.get("actionId"), str):
            raise ValueError("Invalid stored action ID")

        if not isinstance(proposal.get("action"), str):
            raise ValueError("Invalid stored action")

        if not isinstance(proposal.get("facts"), dict):
            raise ValueError("Invalid stored facts")

        if not isinstance(proposal.get("evidenceRefs"), list):
            raise ValueError("Invalid stored evidence")

        proposal_map[package_id] = proposal

    result_map = {}

    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Invalid result entry")

        package_id = result.get("packageId")

        if not isinstance(package_id, str) or not package_id:
            raise ValueError("Invalid package ID")

        if package_id in result_map:
            raise ValueError("Duplicate package result")

        if package_id not in proposal_map:
            raise ValueError("Unknown package")

        proposal = proposal_map[package_id]

        if result.get("actionId") != proposal["actionId"]:
            raise ValueError("Action ID mismatch")

        if result.get("action") != proposal["action"]:
            raise ValueError("Action mismatch")

        if result.get("outcome") not in ["ACCEPTED", "REJECTED"]:
            raise ValueError("Invalid outcome")

        nonce = result.get("receiptNonce")

        if not isinstance(nonce, str) or not nonce.strip() or len(nonce) > 512:
            raise ValueError("Invalid receipt nonce")

        result_map[package_id] = result

    if set(result_map) != set(proposal_map):
        raise ValueError("Every proposal must have exactly one result")

    executions = []

    for package_id, result in result_map.items():
        if result["outcome"] == "ACCEPTED":
            proposal = proposal_map[package_id]

            executions.append({
                "packageId": package_id,
                "actionId": proposal["actionId"],
                "action": proposal["action"],
                "receiptNonce": result["receiptNonce"],
                "facts": proposal["facts"],
                "evidenceRefs": proposal["evidenceRefs"]
            })

    return {
        "batchId": task.batch_id,
        "executions": executions
    }
