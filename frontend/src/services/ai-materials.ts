import { httpClient } from '@/services/http';
import type {
  CardGenerationResponse,
  MaterialQAResponse,
  MaterialSummaryResponse,
} from '@/types/course';

export function fetchMaterialSummary(materialId: number): Promise<MaterialSummaryResponse> {
  return httpClient.get<MaterialSummaryResponse>(`/materials/${materialId}/summary`);
}

export function generateMaterialSummary(materialId: number): Promise<MaterialSummaryResponse> {
  return httpClient.post<MaterialSummaryResponse>(`/materials/${materialId}/summary`, {});
}

export function fetchMaterialCards(materialId: number): Promise<CardGenerationResponse> {
  return httpClient.get<CardGenerationResponse>(`/materials/${materialId}/cards`);
}

export function generateMaterialCards(materialId: number): Promise<CardGenerationResponse> {
  return httpClient.post<CardGenerationResponse>(`/materials/${materialId}/cards`, {});
}

export function askMaterialQuestion(materialId: number, question: string): Promise<MaterialQAResponse> {
  return httpClient.post<MaterialQAResponse>(`/materials/${materialId}/qa`, { question });
}
