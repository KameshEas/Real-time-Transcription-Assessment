import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface Readiness {
  status: string;
  roles: string[];
  vendors: Record<string, boolean>;
}

export function useReadiness() {
  return useQuery({
    queryKey: ["health", "ready"],
    queryFn: () => apiFetch<Readiness>("/health/ready"),
    retry: 1,
  });
}
