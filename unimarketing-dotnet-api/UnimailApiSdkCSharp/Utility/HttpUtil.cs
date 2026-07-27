using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Text;
using System.Web;
using Unimarketing.UnimailApiSdk.CSharp.Utility;

namespace Unimarketing.UnimailApiSdk.CSharp
{
    public enum MethodType
    {
        POST,
        GET,
        PUT,
        DELETE
    }

    public class HttpUtil
    {
        public static string Send(string targetUrl)
        {
            return Send(targetUrl, MethodType.GET, null, null, null, null, null, null);
        }

        public static string Send(string targetUrl, string strPostdata)
        {
            return Send(targetUrl, MethodType.POST, null, null, null, null, null, strPostdata);
        }

        public static string Send(string targetUrl, MethodType? methodType, string accept, string contentType,
                                  string userAgent, Encoding encoding, CookieContainer cookies, string strPostdata)
        {
            if (string.IsNullOrEmpty(targetUrl))
            {
                return string.Empty;
            }

            string paramString = GenQueryPar(null);


            string url = targetUrl;

            if (targetUrl.IndexOf("?") > 0)
            {
                url += "&" + paramString;
            }
            else
            {
                url += "?" + paramString;
            }

            var request = (HttpWebRequest) WebRequest.Create(url);
            request.Method = methodType.ToString();
            request.ContentType = "application/atom+xml";
            request.Headers.Add("Authorization", "OAuth");
            request.Headers.Add("Accept-Encoding", "gzip, deflate");

            if (methodType == MethodType.POST)
            {
                byte[] byteArray = Encoding.UTF8.GetBytes(strPostdata);
                request.ContentLength = byteArray.Length;
                Stream datastream = request.GetRequestStream();
                datastream.Write(byteArray, 0, byteArray.Length);
                datastream.Close();
            }

            string resultData = null;
            using (var response = (HttpWebResponse) request.GetResponse())
            {
                HttpStatusCode status = response.StatusCode;

                if (status == HttpStatusCode.OK || status == HttpStatusCode.Created || status == HttpStatusCode.Accepted)
                {
                    Stream resposeStream = response.GetResponseStream();

                    if (resposeStream != null)
                    {
                        using (var rs = new GZipStream(resposeStream, CompressionMode.Decompress))
                        {
                            var streamReader = new StreamReader(rs, Encoding.UTF8);
                            resultData = streamReader.ReadToEnd();
                        }
                    }

                    return resultData;
                }
                if (status == HttpStatusCode.BadRequest)
                {
                    throw new Exception("请求的地址不存在或者包含不支持的参数");
                }
                if (status == HttpStatusCode.Unauthorized)
                {
                    throw new Exception("未授权");
                }
                if (status == HttpStatusCode.Forbidden)
                {
                    throw new Exception("被禁止访问");
                }
                if (status == HttpStatusCode.NotFound)
                {
                    throw new Exception("请求的资源不存在");
                }
                if (status == HttpStatusCode.MethodNotAllowed)
                {
                    throw new Exception("被列入黑名单");
                }
                if (status == HttpStatusCode.InternalServerError)
                {
                    throw new Exception("内部错误");
                }
                throw new Exception("其他不明错误");
            }
        }

        public static string GenQueryPar(IDictionary<string, string> paramMap)
        {
            IList<string> list = new List<string>();

            if (paramMap != null && paramMap.Count > 0)
            {
                PUTParam(list, paramMap, "q");
                PUTParam(list, paramMap, "field");
                PUTParam(list, paramMap, "preview");
                PUTParam(list, paramMap, "cancel");
                PUTParam(list, paramMap, "type");
                PUTParam(list, paramMap, "start-index");
                PUTParam(list, paramMap, "max-results");
                PUTParam(list, paramMap, "status");
                PUTParam(list, paramMap, "start-date");
                PUTParam(list, paramMap, "finish-date");
            }

            list.Add("apikey=" + GetEncodeValue(Config.APIKEY));
            list.Add("oauth_signature_method=" + GetEncodeValue("HMAC-SHA1"));
            list.Add("oauth_consumer_key=" + GetEncodeValue(Config.APIKEY));
            list.Add("alt=" + GetEncodeValue("atom"));

            string oauthTimestamp = DateTimeExtensions.CurrentTimeMillis() + "";
            String oauthNonce = Guid.NewGuid().ToString();

            list.Add("oauth_timestamp=" + oauthTimestamp);
            list.Add("oauth_nonce=" + GetEncodeValue(oauthNonce));

            var host = new Uri(Config.APIURL);
            int port = host.Port;
            string hostStr;
            if (80 == port)
            {
                hostStr = host.Host;
            }
            else
            {
                hostStr = host.Host + ":" + port;
            }
            var p = new Dictionary<string, string>
                {
                    {"Authorization", "OAuth"},
                    {"Host", hostStr},
                    {"Content-Type", "application/atom+xml"},
                    {"oauth_signature_method", "HMAC-SHA1"},
                    {"oauth_timestamp", oauthTimestamp},
                    {"oauth_nonce", oauthNonce}
                };

            // 计算签名值
            string oauthSignature = SignatureUtil.Sign("http://" + Config.APIKEY, Config.APISECRET, p);

            list.Add("oauth_signature=" + GetEncodeValue(oauthSignature));

            var sb = new StringBuilder();

            for (var i = 0; i < list.Count; i++)
            {
                if (i > 0)
                {
                    sb.Append("&");
                }
                sb.Append(list[i]);
            }

            return sb.ToString();
        }

        private static void PUTParam(IList<string> list, IDictionary<string, string> map, string key)
        {
            if (map[key] != null)
            {
                list.Add(key + "=" + map[key]);
            }
        }

        public static string GetEncodeValue(string param)
        {
            if (string.IsNullOrEmpty(param))
            {
                return string.Empty;
            }
            var sb = new StringBuilder();
            for (int i = 0; i < param.Length; i++)
            {
                string t = param[i].ToString();
                string k = HttpUtility.UrlEncode(t, Encoding.UTF8);
                sb.Append(t == k ? t : k.ToUpper());
            }
            return sb.ToString();
        }
    }
}