import React, { useState } from 'react';
import { View, Text, TextInput, FlatList, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { getPatients } from '../api/patients';
import { Search, Plus, User as UserIcon } from 'lucide-react-native';

export default function PatientsScreen({ navigation }: any) {
  const [search, setSearch] = useState('');
  
  const { data: patients, isLoading, error } = useQuery({
    queryKey: ['patients'],
    queryFn: getPatients,
  });

  const filteredPatients = patients?.filter(p => 
    p.first_name.toLowerCase().includes(search.toLowerCase()) || 
    p.last_name.toLowerCase().includes(search.toLowerCase())
  );

  const getInitials = (first: string, last: string) => {
    return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
  };

  const renderItem = ({ item }: { item: any }) => (
    <TouchableOpacity 
      className="bg-white p-4 mb-3 rounded-xl shadow-sm border border-gray-100 flex-row items-center"
      onPress={() => {
        // Navigate to details in future
      }}
    >
      <View className="w-12 h-12 bg-blue-100 rounded-full items-center justify-center mr-4">
        <Text className="text-blue-700 font-bold text-lg">
          {getInitials(item.first_name, item.last_name)}
        </Text>
      </View>
      <View className="flex-1">
        <Text className="text-lg font-semibold text-gray-800">{item.first_name} {item.last_name}</Text>
        <Text className="text-gray-500 text-sm">{item.contact_number} • {item.dob}</Text>
      </View>
      <View className="items-end">
        <View className="bg-blue-50 px-2 py-1 rounded-full mb-1">
          <Text className="text-blue-700 text-xs font-medium">{item.gender}</Text>
        </View>
        {item.blood_group ? (
          <View className="bg-red-50 px-2 py-1 rounded-full">
            <Text className="text-red-700 text-xs font-bold">{item.blood_group}</Text>
          </View>
        ) : null}
      </View>
    </TouchableOpacity>
  );

  return (
    <View className="flex-1 bg-gray-50 px-4 pt-4">
      {/* Search Bar */}
      <View className="flex-row items-center bg-white border border-gray-200 rounded-xl px-4 py-3 mb-6 shadow-sm">
        <Search size={20} color="#9ca3af" />
        <TextInput
          className="flex-1 ml-3 text-base text-gray-800"
          placeholder="Search patients..."
          value={search}
          onChangeText={setSearch}
        />
      </View>

      {/* Patient List */}
      {isLoading ? (
        <View className="flex-1 justify-center items-center">
          <ActivityIndicator size="large" color="#2563eb" />
        </View>
      ) : error ? (
        <View className="flex-1 justify-center items-center">
          <Text className="text-red-500 text-center">Failed to load patients. Please check your connection.</Text>
        </View>
      ) : filteredPatients?.length === 0 ? (
        <View className="flex-1 justify-center items-center">
          <UserIcon size={48} color="#d1d5db" />
          <Text className="text-gray-500 font-medium mt-4 text-lg">No patients found</Text>
        </View>
      ) : (
        <FlatList
          data={filteredPatients}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingBottom: 80 }}
        />
      )}

      {/* FAB */}
      <TouchableOpacity 
        className="absolute bottom-6 right-6 w-14 h-14 bg-blue-600 rounded-full items-center justify-center shadow-lg"
        onPress={() => {
          // Open Add Patient Modal or Screen
        }}
      >
        <Plus size={24} color="white" />
      </TouchableOpacity>
    </View>
  );
}
