using System;
using System.IO;
using System.ServiceModel.Syndication;
using System.Xml;
using Unimarketing.UnimailApiSdk.CSharp;
using Unimarketing.UnimailApiSdk.CSharp.Model;

namespace UnimailApiSdkCsharpExample
{
    internal class Program
    {
        private static void Main(string[] args)
        {
            var client = UnimailClient.Instance();

            // ================== 获取账户信息 ==================
            /*
            var ca = client.GetAccountInfo();
            Console.WriteLine(ca.ToString());
            */
            // =================================================
            
            // ================== 发送交易邮件 ==================
            /*
            var msr = new MessageSendReq();
		    msr.Subject = "触发测试第一封sdk触发";
		    msr.From = "guang.hu@unimarketing.com.cn"; // 【选填】 from 地址
		    msr.Reply = "guang.hu@unimarketing.com.cn"; // 【选填】回复地址
		    msr.ListName = "list_test"; // 【必填】列表名称

		    msr.Content = "<a href='www.unimarketing.com.cn' link='link1'>Unimarketing</a><br><a href='www.google.com' link='link2'>Google</a>";// 邮件内容
		    msr.ContentType = "html";// 邮件类型
		    msr.To = "370049196@qq.com";// 收件人
		    msr.MessageName = "触发测试第一封0101";// 邮件名称

		    var res = client.MessageSend(msr);
            Console.WriteLine(res.ToString());
            //*/
            // =================================================

            var ca = client.QueryReportEventDeliveryDetail("2013-10-17 00:00:00", "2013-10-17 23:59:59", 1, 50);

            // Console.WriteLine(ca);

            Console.Read();
        }
    }
}