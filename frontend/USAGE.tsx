
// Example usage inside the existing Karamad Received Cheques page:
//
// const [statusFilter, setStatusFilter] =
//   useState<ReceivedChequeStatusFilter>("all");
//
// const params = new URLSearchParams();
// if (statusFilter !== "all") params.set("status", statusFilter);
//
// fetch(`/api/v1/treasury/cheques/received?${params.toString()}`);
//
// Render:
// <ReceivedChequeStatusFilter
//   value={statusFilter}
//   onChange={setStatusFilter}
// />
//
// The existing table/card design remains unchanged.
// The filter only changes which rows are returned/displayed.
