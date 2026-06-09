import React, { useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { getAppointments } from '../api/appointments';
import { Calendar as CalendarIcon, Clock, User as UserIcon } from 'lucide-react-native';

export default function AppointmentsScreen() {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);

  const { data: appointments, isLoading, error } = useQuery({
    queryKey: ['appointments', selectedDate],
    queryFn: () => getAppointments({ appointment_date: selectedDate }),
  });

  const adjustDate = (days: number) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + days);
    setSelectedDate(d.toISOString().split('T')[0]);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Ongoing': return 'bg-blue-100 text-blue-700';
      case 'Completed': return 'bg-emerald-100 text-emerald-700';
      case 'Cancelled': return 'bg-red-100 text-red-700';
      case 'No Show': return 'bg-gray-200 text-gray-700';
      case 'Waiting': return 'bg-amber-100 text-amber-700';
      default: return 'bg-gray-100 text-gray-700';
    }
  };

  const formatTime = (timeString: string) => {
    if (!timeString) return '';
    const date = new Date(timeString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const renderItem = ({ item }: { item: any }) => (
    <TouchableOpacity className="bg-white p-4 mb-3 rounded-xl shadow-sm border border-gray-100 flex-row">
      <View className="mr-4 items-center justify-center border-r border-gray-100 pr-4 w-20">
        <Clock size={20} color="#6b7280" />
        <Text className="text-gray-800 font-bold mt-1">{formatTime(item.appointment_time)}</Text>
      </View>
      <View className="flex-1">
        <Text className="text-lg font-semibold text-gray-800">
          {item.patient?.first_name} {item.patient?.last_name}
        </Text>
        <Text className="text-gray-500 text-sm mt-1">Dr. {item.doctor?.username}</Text>
        <Text className="text-gray-400 text-xs mt-1">{item.appointment_type?.name || 'General Visit'}</Text>
      </View>
      <View className="justify-start items-end">
        <View className={`px-2 py-1 rounded-full ${getStatusColor(item.status).split(' ')[0]}`}>
          <Text className={`text-xs font-bold ${getStatusColor(item.status).split(' ')[1]}`}>
            {item.status}
          </Text>
        </View>
      </View>
    </TouchableOpacity>
  );

  return (
    <View className="flex-1 bg-gray-50 px-4 pt-4">
      {/* Date Selector */}
      <View className="flex-row items-center justify-between bg-white border border-gray-200 rounded-xl px-2 py-2 mb-6 shadow-sm">
        <TouchableOpacity className="p-2" onPress={() => adjustDate(-1)}>
          <Text className="text-gray-500 text-xl font-bold">‹</Text>
        </TouchableOpacity>
        <View className="flex-row items-center">
          <CalendarIcon size={16} color="#4361ee" className="mr-2" />
          <Text className="text-gray-800 font-semibold mx-2">{selectedDate}</Text>
        </View>
        <TouchableOpacity className="p-2" onPress={() => adjustDate(1)}>
          <Text className="text-gray-500 text-xl font-bold">›</Text>
        </TouchableOpacity>
      </View>

      {/* Appointments List */}
      {isLoading ? (
        <View className="flex-1 justify-center items-center">
          <ActivityIndicator size="large" color="#4361ee" />
        </View>
      ) : error ? (
        <View className="flex-1 justify-center items-center">
          <Text className="text-red-500 text-center">Failed to load appointments.</Text>
        </View>
      ) : appointments?.length === 0 ? (
        <View className="flex-1 justify-center items-center">
          <CalendarIcon size={48} color="#d1d5db" />
          <Text className="text-gray-500 font-medium mt-4 text-lg">No appointments today</Text>
        </View>
      ) : (
        <FlatList
          data={appointments}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingBottom: 80 }}
        />
      )}
    </View>
  );
}
