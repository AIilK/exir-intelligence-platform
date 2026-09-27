
# Add these imports/logic to the existing received-cheques route.
# Keep your existing SQL query and response shape unchanged.

from app.services.v161_received_cheque_filter import filter_received_cheques

# Example:
#
# @router.get("/received-cheques")
# def received_cheques(status: str | None = None):
#     rows = existing_karamad_received_cheques_query()
#     filtered = filter_received_cheques(rows, status)
#     return {
#         "status": "success",
#         "source": "KARAMAD",
#         "items": filtered,
#         "count": len(filtered),
#     }
#
# If your current endpoint already has a response wrapper, only apply:
#
#     rows = filter_received_cheques(rows, status)
#
# Do NOT change the SQL source query for this feature.
