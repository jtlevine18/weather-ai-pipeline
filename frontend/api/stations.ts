import type { VercelRequest, VercelResponse } from '@vercel/node'

const STATIONS = [
  { id: "KL_TVM", name: "Thiruvananthapuram", lat: 8.4833, lon: 76.9500, state: "Kerala", altitude_m: 60 },
  { id: "KL_COK", name: "Kochi", lat: 9.9500, lon: 76.2667, state: "Kerala", altitude_m: 1 },
  { id: "KL_ALP", name: "Alappuzha", lat: 9.5500, lon: 76.4167, state: "Kerala", altitude_m: 2 },
  { id: "KL_KNR", name: "Kannur", lat: 11.8333, lon: 75.3333, state: "Kerala", altitude_m: 11 },
  { id: "KL_KZD", name: "Kozhikode", lat: 11.2500, lon: 75.7833, state: "Kerala", altitude_m: 4 },
  { id: "KL_TCR", name: "Thrissur", lat: 10.5167, lon: 76.2167, state: "Kerala", altitude_m: 40 },
  { id: "KL_KTM", name: "Kottayam", lat: 9.5833, lon: 76.5167, state: "Kerala", altitude_m: 39 },
  { id: "KL_PKD", name: "Palakkad", lat: 10.7667, lon: 76.6500, state: "Kerala", altitude_m: 95 },
  { id: "KL_PNL", name: "Punalur", lat: 9.0000, lon: 76.9167, state: "Kerala", altitude_m: 33 },
  { id: "KL_NLB", name: "Nilambur", lat: 11.2800, lon: 76.2300, state: "Kerala", altitude_m: 30 },
  { id: "TN_TNJ", name: "Thanjavur", lat: 10.7833, lon: 79.1333, state: "Tamil Nadu", altitude_m: 0 },
  { id: "TN_MDU", name: "Madurai", lat: 9.8333, lon: 78.0833, state: "Tamil Nadu", altitude_m: 139 },
  { id: "TN_TRZ", name: "Tiruchirappalli", lat: 10.7667, lon: 78.7167, state: "Tamil Nadu", altitude_m: 85 },
  { id: "TN_SLM", name: "Salem", lat: 11.6500, lon: 78.1667, state: "Tamil Nadu", altitude_m: 279 },
  { id: "TN_ERD", name: "Erode", lat: 11.3400, lon: 77.7200, state: "Tamil Nadu", altitude_m: 183 },
  { id: "TN_CHN", name: "Chennai", lat: 13.0000, lon: 80.1833, state: "Tamil Nadu", altitude_m: 10 },
  { id: "TN_TNV", name: "Tirunelveli", lat: 8.7333, lon: 77.7500, state: "Tamil Nadu", altitude_m: 45 },
  { id: "TN_CBE", name: "Coimbatore", lat: 11.0333, lon: 77.0500, state: "Tamil Nadu", altitude_m: 396 },
  { id: "TN_VLR", name: "Vellore", lat: 12.9200, lon: 79.1300, state: "Tamil Nadu", altitude_m: 215 },
  { id: "TN_NGP", name: "Nagappattinam", lat: 10.7667, lon: 79.8500, state: "Tamil Nadu", altitude_m: 2 },
]

export default function handler(_req: VercelRequest, res: VercelResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.json(STATIONS)
}
