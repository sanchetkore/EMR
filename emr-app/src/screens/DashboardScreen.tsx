import React from 'react';
import { View, Text, ScrollView } from 'react-native';
import { useAuthStore } from '../store/authStore';
import { LogOut, Users, Calendar, Activity } from 'lucide-react-native';
import { TouchableOpacity } from 'react-native';

export default function DashboardScreen() {
  const { user, logout } = useAuthStore();

  const StatCard = ({ title, value, icon: Icon, color }: any) => (
    <View className="bg-white p-4 rounded-xl shadow-sm border border-gray-100 flex-1 mx-1 mb-2">
      <View className="flex-row justify-between items-center mb-2">
        <Text className="text-gray-500 text-sm font-medium">{title}</Text>
        <View className={`p-2 rounded-full ${color}`}>
          <Icon size={16} color="white" />
        </View>
      </View>
      <Text className="text-2xl font-bold text-gray-800">{value}</Text>
    </View>
  );

  return (
    <ScrollView className="flex-1 bg-gray-50 px-4 pt-6">
      <View className="flex-row justify-between items-center mb-8">
        <View>
          <Text className="text-gray-500 text-sm">Welcome back,</Text>
          <Text className="text-2xl font-bold text-gray-800">Dr. {user?.username}</Text>
        </View>
        <TouchableOpacity 
          className="bg-red-50 p-2 rounded-full border border-red-100"
          onPress={logout}
        >
          <LogOut size={20} color="#dc2626" />
        </TouchableOpacity>
      </View>

      <Text className="text-lg font-semibold text-gray-800 mb-4">Today's Overview</Text>
      
      <View className="flex-row justify-between mb-2">
        <StatCard title="Patients" value="12" icon={Users} color="bg-blue-500" />
        <StatCard title="Appointments" value="8" icon={Calendar} color="bg-emerald-500" />
      </View>
      <View className="flex-row justify-between mb-6">
        <StatCard title="Pending Labs" value="3" icon={Activity} color="bg-amber-500" />
        <StatCard title="Revenue" value="$450" icon={Activity} color="bg-purple-500" />
      </View>

      <Text className="text-lg font-semibold text-gray-800 mb-4">Recent Appointments</Text>
      <View className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 mb-10">
        <Text className="text-gray-500 text-center py-4">No recent appointments today.</Text>
      </View>
    </ScrollView>
  );
}
