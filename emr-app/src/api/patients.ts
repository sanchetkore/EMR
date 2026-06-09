import { apiClient } from './config';
import { Patient, PatientInput } from '../types';

export const getPatients = async () => {
  const { data } = await apiClient.get<Patient[]>('/api/patients');
  return data;
};

export const getPatientById = async (id: number) => {
  const { data } = await apiClient.get<Patient>(`/api/patients/${id}`);
  return data;
};

export const createPatient = async (patient: PatientInput) => {
  const { data } = await apiClient.post<Patient>('/api/patients', patient);
  return data;
};

export const updatePatient = async (id: number, patient: PatientInput) => {
  const { data } = await apiClient.put<Patient>(`/api/patients/${id}`, patient);
  return data;
};
