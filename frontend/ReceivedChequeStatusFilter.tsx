
import React from "react";

export type ReceivedChequeStatusFilter = "all" | "uncertain";

type Props = {
  value: ReceivedChequeStatusFilter;
  onChange: (value: ReceivedChequeStatusFilter) => void;
};

export default function ReceivedChequeStatusFilter({
  value,
  onChange,
}: Props) {
  return (
    <div className="received-cheque-filter">
      <label htmlFor="received-cheque-status">وضعیت چک</label>
      <select
        id="received-cheque-status"
        value={value}
        onChange={(e) =>
          onChange(e.target.value as ReceivedChequeStatusFilter)
        }
      >
        <option value="all">همه</option>
        <option value="uncertain">غیرقطعی</option>
      </select>
    </div>
  );
}
