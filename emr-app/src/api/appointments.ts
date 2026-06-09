import { apiClient } from './config';
import { Appointment, AppointmentInput, AppointmentsQuery } from '../types';

export const getAppointments = async (params?: AppointmentsQuery) => {
  const { data } = await apiClient.get<Appointment[]>('/api/appointments', { params });
  return data;
};

export const getAppointmentById = async (id: number) => {
  const { data } = await apiClient.get<Appointment>(`/api/appointments/${id}`);
  return data;
};

export const createAppointment = async (appointment: AppointmentInput) => {
  const { data } = await apiClient.post<Appointment>('/api/appointments', appointment);
  return data;
};

export const updateAppointment = async (id: number, appointment: AppointmentInput) => {
  const { data } = await apiClient.put<Appointment>(`/api/appointments/${id}`, appointment);
  return data;
};
