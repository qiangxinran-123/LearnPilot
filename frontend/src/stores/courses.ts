import { computed, ref } from 'vue';
import { defineStore } from 'pinia';

import { fetchCourses } from '@/services/courses';
import { normalizeApiError } from '@/services/http';
import type { CourseSummary } from '@/types/course';

type CourseLoadState = 'idle' | 'loading' | 'success' | 'error';

export const useCourseStore = defineStore('courses', () => {
  const courses = ref<CourseSummary[]>([]);
  const state = ref<CourseLoadState>('idle');
  const errorMessage = ref('');
  let pendingRequest: Promise<void> | undefined;

  const isLoading = computed(() => state.value === 'loading');
  const hasError = computed(() => state.value === 'error');

  async function loadCourses(force = false): Promise<void> {
    if (pendingRequest && !force) {
      return pendingRequest;
    }

    if (state.value === 'success' && !force) {
      return;
    }

    state.value = 'loading';
    errorMessage.value = '';

    pendingRequest = fetchCourses()
      .then((response) => {
        courses.value = response.courses;
        state.value = 'success';
      })
      .catch((error: unknown) => {
        courses.value = [];
        state.value = 'error';
        errorMessage.value = normalizeApiError(error).message;
      })
      .finally(() => {
        pendingRequest = undefined;
      });

    return pendingRequest;
  }

  return {
    courses,
    state,
    errorMessage,
    isLoading,
    hasError,
    loadCourses,
  };
});
