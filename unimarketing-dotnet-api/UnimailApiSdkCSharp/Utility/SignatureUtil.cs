using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

namespace Unimarketing.UnimailApiSdk.CSharp.Utility
{
    public class SignatureUtil
    {
        public static string Sign(string domain, string secretKey, IDictionary<string, string> paramMap)
        {
            string data = domain + "?" + sort(paramMap);

            return HmacSHA1(data, secretKey);
        }

        public static string HmacSHA1(string data, string key)
        {
            //Console.WriteLine(data);

            //Console.WriteLine();

            var encoding = new ASCIIEncoding();

            var hmacsha1 = new HMACSHA1(encoding.GetBytes(key));
            byte[] hash = hmacsha1.ComputeHash(encoding.GetBytes(data));

            string result = Convert.ToBase64String(hash);

            //Console.WriteLine(result);

            //Console.WriteLine();

            return result;
        }

        private static string sort(IDictionary<string, string> paramMap)
        {
            List<string> list = paramMap.Keys.ToList();
            list.Sort();

            var sb = new StringBuilder();
            foreach (string key in list)
            {
                sb.Append(key + "=" + paramMap[key] + "&");
            }

            return sb.ToString();
        }

        public static byte[] GetBytes(string s)
        {
            return Encoding.UTF8.GetBytes(s);
        }
    }
}