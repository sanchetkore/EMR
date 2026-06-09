// Central domain types mirroring the EMR backend (FastAPI) response/request schemas.
// These describe the JSON shapes exchanged over `/api`.

// ─── Auth, Users, Roles & Permissions ──────────────────────────────────────────

export interface Permission {
  id: number
  name: string
  description: string | null
}

export interface Role {
  id: number
  name: string
  permissions: Permission[]
}

export interface User {
  id: number
  username: string
  email: string
  is_active: boolean
  role_id: number | null
  role?: Role | null
  signature_path?: string | null
}

export interface UserInput {
  username: string
  email: string
  password?: string
  role_id: number | null
  is_active: boolean
}

export interface RoleInput {
  name: string
  permission_ids: number[]
}

export interface PermissionInput {
  name: string
  description?: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

// ─── Patients ───────────────────────────────────────────────────────────────

export interface Patient {
  id: number
  first_name: string
  last_name: string
  dob: string
  gender: string
  contact_number: string
  email: string | null
  blood_group: string | null
  emergency_contact: string | null
  emergency_phone: string | null
  address: string | null
  language: string | null
  is_active: number
}

export interface PatientInput {
  first_name: string
  last_name: string
  dob: string
  gender: string
  contact_number: string
  email?: string
  blood_group?: string
  emergency_contact?: string
  emergency_phone?: string
  address?: string
  language?: string
  is_active?: number
}

// ─── Appointments ─────────────────────────────────────────────────────────────

export interface AppointmentType {
  id: number
  name: string
  rate: number
  is_active: number
}

export interface AppointmentTypeInput {
  name: string
  rate: number
  is_active?: number
}

export interface AppointmentStatusConfig {
  id: number
  name: string
  color: string | null
  is_active: number
}

export interface AppointmentStatusInput {
  name: string
  color?: string
  is_active?: number
}

export interface Appointment {
  id: number
  patient_id: number
  doctor_id: number
  appointment_type_id: number | null
  appointment_time: string
  status: string
  patient?: Patient
  doctor?: User
  appointment_type?: AppointmentType | null
}

export interface AppointmentInput {
  patient_id: number
  doctor_id: number
  appointment_type_id: number | null
  appointment_time: string
  status: string
}

export interface AppointmentsQuery {
  patient_id?: number
  doctor_id?: number
  appointment_date?: string
  status?: string
}

// ─── Billing ───────────────────────────────────────────────────────────────

export interface InvoiceItem {
  id: number
  invoice_id: number
  service_name: string
  quantity: number
  unit_price: number
}

export interface InvoiceItemInput {
  service_name: string
  quantity: number
  unit_price: number
}

export interface Invoice {
  id: number
  patient_id: number
  appointment_id: number | null
  amount: number
  status: string
  items: InvoiceItem[]
}

export interface InvoiceInput {
  patient_id: number
  appointment_id?: number
  amount: number
  status: string
  items: InvoiceItemInput[]
}

export interface BillSuggestionItem {
  service_name: string
  quantity: number
  unit_price: number
  total_price: number
}

export interface BillSuggestion {
  appointment_id: number
  patient_id: number
  items: BillSuggestionItem[]
  total_amount: number
}

// ─── Settings ───────────────────────────────────────────────────────────────

export interface SystemSetting {
  key: string
  value: string
}

export type SettingsMap = Record<string, string>

// ─── Vitals, Visits & Encounters ──────────────────────────────────────────────

export interface VitalConfig {
  id: number
  name: string
  data_type: string
  formula?: string | null
}

export interface VitalEntry {
  id?: number
  vital_config_id: number
  value: string
}

export interface Complaint {
  id?: number
  complaint: string
  from_date?: string
  duration?: string
}

export interface Diagnosis {
  id?: number
  diagnosis: string
  date?: string
}

export interface Treatment {
  id?: number
  treatment: string
  due_date?: string
}

export interface PrescriptionInput {
  name: string
  morning: string
  afternoon: string
  evening: string
  night: string
  when: string
  details: string
}

export interface Encounter {
  id: number
  visit_number: number
  encounter_date: string
  status: string
  reason?: string | null
  notes?: string | null
  quick_notes?: string | null
  advice?: string | null
}

export interface PrescriptionItem {
  id?: number
  prescription_id?: number
  molecule?: string
  name: string
  morning: string
  afternoon: string
  evening: string
  night: string
  when: string
  details: string
}

export interface Prescription {
  id: number
  patient_id: number
  encounter_id: number
  doctor_id: number
  notes?: string
  date_prescribed: string
  items: PrescriptionItem[]
}

export interface VisitResponse {
  encounter: Encounter
  vitals: VitalEntry[]
  complaints: Complaint[]
  diagnoses: Diagnosis[]
  treatments: Treatment[]
  prescriptions?: Prescription[]
}

export interface VisitPayload {
  patient_id: number
  doctor_id: number
  appointment_id: number | null
  status: string
  reason: string | null
  notes: string | null
  quick_notes: string | null
  advice: string | null
  vitals: { vital_config_id: number; value: string }[]
  complaints: Complaint[]
  diagnoses: Diagnosis[]
  treatments: Treatment[]
  lab_test_catalogs: number[]
  prescriptions: PrescriptionInput[]
}

// ─── Lab Tests & Catalog ──────────────────────────────────────────────────────

export interface LabCatalogItem {
  id: number
  name: string
  description: string | null
  price: number
  unit: string | null
  min_value: number | null
  max_value: number | null
  is_active: boolean
}

export interface LabComboCatalogItem {
  id: number
  name: string
  description: string | null
  price: number
  is_active: boolean
}

export interface OrderComboPayload {
  patient_id: number
  combo_id: number
}

export interface LabQueueResponseItem {
  lab_result: LabResult
  patient: Patient
}

export interface LabCatalogInput {
  name: string
  description?: string | null
  price: number
  is_active: boolean
}

export interface LabResult {
  id: number
  patient_id: number
  encounter_id: number | null
  catalog_id: number | null
  test_name: string
  result_value: string | null
  unit: string | null
  reference_range: string | null
  status: string
  notes: string | null
  cost: number | null
  ordered_by: number | null
  ordered_date: string
  result_date?: string | null
  patient?: Patient
}

export interface LabResultInput {
  test_name: string
  result_value?: string
  unit?: string
  reference_range?: string
  status: string
  notes?: string
  patient_id: number
  encounter_id?: number | null
  catalog_id?: number | null
  cost?: number | null
  ordered_by?: number | null
}

// ─── Drugs ───────────────────────────────────────────────────────────────────

export interface Drug {
  id: number
  name: string
  generic_name: string | null
  form: string | null
  strength: string | null
  manufacturer: string | null
  is_active: boolean
}

export interface DrugInput {
  name: string
  generic_name?: string
  form?: string
  strength?: string
  manufacturer?: string
  is_active: boolean
}

// ─── Live Queue (waiting-room TV display) ──────────────────────────────────────

export interface QueueEntry {
  appointment_id: number
  patient_name: string
  doctor_name: string
  time: string
  status: string
}

export interface LiveQueue {
  ongoing: QueueEntry[]
  waiting: QueueEntry[]
}
e x p o r t  
 i n t e r f a c e  
 C l i n i c  
   i d :   n u m b e r ;   n a m e :   s t r i n g ;   a d d r e s s :   s t r i n g ;   s u p p o r t _ e m a i l :   s t r i n g ;   p h o n e :   s t r i n g ;   w h a t s a p p :   s t r i n g ;   w e b s i t e :   s t r i n g ;    
 a p p _ l i n k :   s t r i n g ;   l o g o _ p a t h :   s t r i n g ;    
 e x p o r t  
 i n t e r f a c e  
 C l i n i c I n p u t  
   n a m e :   s t r i n g ;   a d d r e s s :   s t r i n g ;   s u p p o r t _ e m a i l :   s t r i n g ;   p h o n e :   s t r i n g ;   w h a t s a p p :   s t r i n g ;   w e b s i t e :   s t r i n g ;   a p p _ l i n k :    
 s t r i n g ;    
 