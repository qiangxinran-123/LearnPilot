import { httpClient } from '@/services/http';
import type {
  Material,
  MaterialContentResponse,
  MaterialListResponse,
} from '@/types/course';

export function fetchMaterials(courseId: number): Promise<MaterialListResponse> {
  return httpClient.get<MaterialListResponse>(`/courses/${courseId}/materials`);
}

export function fetchMaterial(materialId: number): Promise<Material> {
  return httpClient.get<Material>(`/materials/${materialId}`);
}

export function fetchMaterialContent(
  materialId: number,
  offset = 0,
  limit = 12_000,
): Promise<MaterialContentResponse> {
  return httpClient.get<MaterialContentResponse>(
    `/materials/${materialId}/content?offset=${offset}&limit=${limit}`,
  );
}

export function uploadMaterial(courseId: number, file: File): Promise<Material> {
  const data = new FormData();
  data.append('file', file);
  return httpClient.postForm<Material>(`/courses/${courseId}/materials/upload`, data);
}

export function deleteMaterial(materialId: number): Promise<{ id: number; deleted: boolean }> {
  return httpClient.delete<{ id: number; deleted: boolean }>(`/materials/${materialId}`);
}
