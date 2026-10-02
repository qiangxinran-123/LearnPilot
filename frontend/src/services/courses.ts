import { httpClient } from '@/services/http';
import type {
  CourseDeleteResponse,
  CourseInput,
  CourseListResponse,
  CourseSummary,
} from '@/types/course';

export function fetchCourses(): Promise<CourseListResponse> {
  return httpClient.get<CourseListResponse>('/courses');
}

export function fetchCourse(courseId: number): Promise<CourseSummary> {
  return httpClient.get<CourseSummary>(`/courses/${courseId}`);
}

export function createCourse(payload: CourseInput): Promise<CourseSummary> {
  return httpClient.post<CourseSummary>('/courses', payload);
}

export function updateCourse(courseId: number, payload: CourseInput): Promise<CourseSummary> {
  return httpClient.patch<CourseSummary>(`/courses/${courseId}`, payload);
}

export function deleteCourse(courseId: number): Promise<CourseDeleteResponse> {
  return httpClient.delete<CourseDeleteResponse>(`/courses/${courseId}`);
}
