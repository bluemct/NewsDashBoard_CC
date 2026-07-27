using System;
using System.IO;
using System.ServiceModel.Syndication;
using System.Text;
using System.Xml;
using Unimarketing.UnimailApiSdk.CSharp.Model;
using Unimarketing.UnimailApiSdk.CSharp.Utility;

namespace Unimarketing.UnimailApiSdk.CSharp
{
    public enum AuthModeEnum
    {
        BASIC,
        APIKEY,
        OAUTH
    }

    public class UnimailClient
    {
        private static UnimailClient _instance;

        private static readonly object LockHelper = new object();

        private UnimailClient()
        {
        }

        private UnimailClient(AuthModeEnum authMode, string key, string secret)
        {
            _instance = new UnimailClient {AuthMode = authMode};
            if (authMode == AuthModeEnum.APIKEY)
            {
                _instance.ApiKey = key;
                _instance.ApiSecret = secret;
            }
        }

        public AuthModeEnum AuthMode { get; set; }

        public string ApiKey { get; set; }
        public string ApiSecret { get; set; }

        public static UnimailClient Instance()
        {
            if (_instance == null)
            {
                lock (LockHelper)
                {
                    if (_instance == null)
                    {
                        _instance = new UnimailClient(Config.AUTHMODE, Config.APIKEY, Config.APISECRET);
                    }
                }
            }
            return _instance;
        }


        public Account GetAccountInfo()
        {
            string response = HttpUtil.Send(Config.APIURL + Config.UM_ACCOUNT);
            
            if (!string.IsNullOrEmpty(response))
            {
                return ClientUtils.ParseAccountInfo(response);
            }
            return null;
        }

        public MessageSendRes MessageSend(MessageSendReq messageSendReq) 
        {
            var res = new MessageSendRes();

            var entry = ClientUtils.OrgMessageSendMail(messageSendReq);

            string response = HttpUtil.Send(Config.APIURL + Config.UM_MESSAGE_SEND, entry);

            res = ClientUtils.ParseMessageSendMailResponse(response);

		    return res;
	    }

        public ReportEventDeliveryDetail QueryReportEventDeliveryDetail(string startTime, string finishTime, int startIndex, int maxResults)
        {
            var res = new ReportEventDeliveryDetail();

            string url = Config.APIURL + Config.UM_REPORT_EVENT_DELIVERY_DETAIL;
            url = url + "?start-date=" + startTime + "&finish-date=" + finishTime + "&start-index=" + startIndex + "&max-results=" + maxResults;

            string response = HttpUtil.Send(url);

            res = ClientUtils.ParseReportEventDeliveryDetail(response);

            return res;
	    }

    }
}