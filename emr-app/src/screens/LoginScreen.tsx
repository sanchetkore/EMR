import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, Alert } from 'react-native';
import { useAuthStore } from '../store/authStore';
import { apiClient } from '../api/config';

export default function LoginScreen() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const setAuth = useAuthStore(state => state.setAuth);

  const handleLogin = async () => {
    if (!username || !password) {
      Alert.alert('Error', 'Please enter both username and password');
      return;
    }
    
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);
      
      const response = await apiClient.post('/api/auth/login', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      
      const token = response.data.access_token;
      const refreshToken = response.data.refresh_token;
      
      // In a real app we'd fetch the user profile here using the token
      // For now we just mock the user
      setAuth(
        { id: 1, username: username, email: 'user@example.com', role_id: 1 },
        token,
        refreshToken
      );
    } catch (error) {
      Alert.alert('Login Failed', 'Invalid credentials or server error.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View className="flex-1 justify-center px-8 bg-gray-50">
      <View className="items-center mb-10">
        <Text className="text-4xl font-bold text-blue-600 mb-2">EMR App</Text>
        <Text className="text-gray-500 text-base">Sign in to your account</Text>
      </View>
      
      <View className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
        <View className="mb-4">
          <Text className="text-sm font-medium text-gray-700 mb-1">Username</Text>
          <TextInput
            className="w-full bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-gray-800"
            placeholder="Enter your username"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
          />
        </View>
        
        <View className="mb-6">
          <Text className="text-sm font-medium text-gray-700 mb-1">Password</Text>
          <TextInput
            className="w-full bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-gray-800"
            placeholder="Enter your password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />
        </View>
        
        <TouchableOpacity
          className="w-full bg-blue-600 rounded-lg py-4 items-center"
          onPress={handleLogin}
          disabled={loading}
        >
          <Text className="text-white font-semibold text-lg">
            {loading ? 'Signing in...' : 'Sign In'}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}
