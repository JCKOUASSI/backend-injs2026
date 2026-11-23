/** Appels API côté client : l'acteur est transporté par en-tête. */
import { acteurCourantId } from "@/components/EnTete";

export async function apiFetch<T = unknown>(
  chemin: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(chemin, {
    ...options,
    headers: {
      "content-type": "application/json",
      "x-acteur-id": String(acteurCourantId()),
      ...(options.headers ?? {}),
    },
  });
  const data = await res.json();
  if (!res.ok) {
    throw Object.assign(new Error(data?.message ?? "Requête refusée"), {
      payload: data,
      status: res.status,
    });
  }
  return data as T;
}

export interface ReponseErreurClient {
  ok: false;
  code: string;
  message: string;
  explication: string;
  action_recommandee: string;
  details?: Record<string, unknown>;
}
